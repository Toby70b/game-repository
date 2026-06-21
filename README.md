# game-repository

An AWS-based pipeline that maintains a DynamoDB table of Steam games. Scheduled Lambda functions keep the data
fresh — one imports new/updated games from the Steam Web API daily, one exports a snapshot of the table to S3, and one
streams new game additions to an SNS topic in real time.

---

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.x
- [Python](https://www.python.org/downloads/) 3.12+
- AWS credentials configured (e.g. via `aws configure` or environment variables)
- A [Steam Web API key](https://steamcommunity.com/dev)

---

## Architecture Overview

![Architecture diagram](./docs/architecture.png)

---

## AWS Resources

| Resource                                          | Description                                                                                                               |
|---------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| `aws_dynamodb_table.games`                        | `Games` table — hash key `game_id` (UUID), GSI on `steam_game_id`, DynamoDB Streams enabled (`NEW_IMAGE`)                |
| `aws_s3_bucket.games_export`                      | Snapshot bucket with versioning and lifecycle rules                                                                       |
| `aws_lambda_function.ddb_import`                  | Imports new Steam games into DynamoDB                                                                                     |
| `aws_lambda_function.ddb_export`                  | Exports the full table to S3 as gzipped NDJSON                                                                            |
| `aws_lambda_function.new_game_item_publisher`     | Reads new-item events from the DynamoDB stream and publishes them to SNS in batches                                       |
| `aws_sns_topic.new_game_items`                    | SNS topic (`new-game-items`) that receives new game item events from the stream publisher                                 |
| `aws_lambda_event_source_mapping` (stream)        | Wires the DynamoDB stream to `new-game-item-publisher` (batch size 100, window 5 s)                                       |
| `aws_scheduler_schedule.daily_ddb_import`         | Triggers import Lambda at **22:00 UTC** daily                                                                             |
| `aws_scheduler_schedule.daily_ddb_export`         | Triggers export Lambda at **00:00 UTC** daily                                                                             |
| `aws_ssm_parameter.steam_api_key`                 | Pre-created manually — Terraform constructs the ARN from known values and never reads the secret, keeping it out of state |

---

## Import Service — Hexagonal Architecture

The `ddb_import` service is structured around hexagonal (ports & adapters) architecture:

- **Domain** (`domain/game.py`) — `Game` dataclass (`steam_game_id`, `game_title`). No framework dependencies.
- **Ports** (`ports.py`) — Abstract interfaces: `ImportGamesUseCase` (inbound), `GameSource` and `GameRepository` (
  outbound).
- **Service** (`game_import_service.py`) — `GameImportService` implements the use case. Fetches all pages from Steam, deduplicates
  against existing records using the highest known `steam_game_id` as a cursor, and writes new games in batches.
- **Adapters**:
    - `adapters/ddb_import.py` — Lambda handler; composes the service and invokes it.
    - `adapters/steam_api.py` — Retrieves the API key from SSM, delegates HTTP to `SteamHttpClient`, maps responses to
      `Game` objects.
    - `adapters/steam_http_client.py` — Builds and sends paginated requests to `IStoreService/GetAppList/v1`, logs
      request/response details (API key is redacted).
    - `adapters/dynamodb_repo.py` — Scans the `gsi_steam_game_id` GSI for deduplication, batch-writes new items using
      `GameItem` as the persistence entity.

---

## Stream Publish Lambda

The `ddb_stream_publish` Lambda (`new-game-item-publisher`) is triggered by the DynamoDB stream on the `Games` table whenever new items are inserted.

- **Trigger** — DynamoDB Streams (`NEW_IMAGE`), event-source mapping with batch size 100 and a 5-second batching window.
- **Processing** — For each record the handler deserialises the DynamoDB JSON `NewImage`, wraps it in a structured game event (fields: `event_id`, `event_name`, `event_timestamp`, `game_data`), and accumulates entries into SNS `publish_batch` calls (max 10 per batch, the SNS limit).
- **Destination** — SNS topic `new-game-items`. Downstream consumers can subscribe to this topic to react to new game additions in real time.
- **Error handling** — Records without a `NewImage` (e.g. deletes/updates that slip through) are logged as warnings and skipped rather than failing the batch.

---

## Getting Started

### 1. Create the Steam API key SSM parameter

The Steam API key is managed outside of Terraform to keep the secret value out of Terraform state. Create it once
before running `terraform apply`:

```bash
aws ssm put-parameter \
  --name "/game-repository/steam-api-key" \
  --value "your-steam-api-key-here" \
  --type SecureString \
  --region your-region-here
```

> The parameter name must match exactly — Terraform references it via a data source at `/game-repository/steam-api-key`.

### 2. Deploy

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Terraform will:

- Create the `Games` DynamoDB table
- Create the S3 snapshot bucket
- Package and deploy both Lambda functions
- Configure EventBridge schedules for both jobs

### 3. When finished destroy

```bash
terraform destroy
```

> The SSM parameter is not managed by Terraform so it will **not** be deleted by `terraform destroy` — remove it
> manually if needed:
> ```bash
> aws ssm delete-parameter --name "/game-repository/steam-api-key" --region eu-west-2
> ```

---

## Lambda Packaging

Both Lambda zip files are built automatically by Terraform's `archive_file` data source — no manual packaging step is
required.

| Lambda                    | Source                                                    |
|---------------------------|-----------------------------------------------------------|
| `ddb-games-export`        | `lambdas/ddb_export/ddb_export.py` (single file)          |
| `ddb-games-import`        | `lambdas/ddb_import/src/` (entire directory)              |
| `new-game-item-publisher` | `lambdas/ddb_stream_publish/ddb_stream_publish.py` (single file) |

---

## Terraform State

Remote state is stored in S3 with native locking:

```hcl
# terraform/backend.tf
backend "s3" {
  bucket       = "terraform-state-<12345678>"
  key          = "terraform.tfstate"
  region       = "eu-west-2"
  encrypt      = true
  use_lockfile = true
}
```
---

## Local Testing

The `docker/` directory contains a Docker Compose stack for testing Lambda interactions locally without a real AWS
account.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running
- [terraform-local](https://docs.localstack.cloud/user-guide/integrations/terraform/) (`pip install terraform-local`)
- A LocalStack account (`LOCALSTACK_AUTH_TOKEN` environment variable must be set, see [LocalStack docs](https://docs.localstack.cloud/getting-started/installation/#docker) for details)

### Start the stack

```bash
cd docker
docker-compose up -d
```

This starts:

| Service         | URL                   | Purpose                                        |
|-----------------|-----------------------|------------------------------------------------|
| LocalStack      | http://localhost:4566 | Mock AWS (DynamoDB, S3, SSM, Lambda, etc.)     |
| WireMock        | http://localhost:8080 | Mock Steam API (stubs in `mappings/` directory)|
| DynamoDB Admin  | http://localhost:8001 | Web UI for browsing DynamoDB tables            |

### Create the Steam API key in LocalStack

The Steam API key is already created in LocalStack by the init script as the SSM parameter
`/game-repository/steam-api-key`, which is the parameter name Terraform configures the Lambda to read. The
actual key value doesn't matter for local testing since WireMock doesn't validate it.

### Deploy infrastructure to LocalStack

Use `tflocal` (a wrapper that auto-configures all LocalStack endpoints):

```bash
cd terraform
tflocal init -reconfigure
tflocal apply -auto-approve -var="steam_api_base_url=http://host.docker.internal:8080"
```

> **Notes:**
> - `host.docker.internal:8080` allows Lambda (running in a container) to reach WireMock on your host
> - LocalStack's EventBridge Scheduler support may be limited; invoke Lambdas manually for testing (see below)

### Invoke Lambdas via AWS CLI

```bash
# Import Lambda (fetches from WireMock)
aws --endpoint-url=http://localhost:4566 --region eu-west-2 lambda invoke \
  --function-name ddb-games-import \
  --payload '{}' \
  /dev/stdout

# Export Lambda (writes to LocalStack S3)
aws --endpoint-url=http://localhost:4566 --region eu-west-2 lambda invoke \
  --function-name ddb-games-export \
  --payload '{}' \
  /dev/stdout
```

> The `new-game-item-publisher` Lambda is triggered automatically by the DynamoDB stream whenever the import Lambda writes new items — no manual invocation is required.

### Verify Data

#### DynamoDB Admin UI
Open http://localhost:8001 in your browser

#### Check DynamoDB via CLI
```bash
aws --endpoint-url=http://localhost:4566 --region eu-west-2 dynamodb scan --table-name Games
```

#### Check S3
```bash
aws --endpoint-url=http://localhost:4566 --region eu-west-2 s3 ls --recursive s3://
```

#### Terraform Desktop

If you prefer a GUI to invoke the lambdas and view the items in the DDB table or S3, [Terraform Desktop](https://www.hashicorp.com/products/terraform/desktop) provides a visual
interface for managing Terraform workflows.

