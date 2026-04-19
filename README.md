# game-repository

An AWS-based pipeline that maintains a DynamoDB table of Steam games. Two scheduled Lambda functions keep the data
fresh — one imports new games from the Steam Web API daily, and one exports a snapshot of the table to S3 for backup.

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

| Resource                                  | Description                                                                                                               |
|-------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| `aws_dynamodb_table.games`                | `Games` table — hash key `game_id` (UUID), GSI on `steam_game_id`                                                         |
| `aws_s3_bucket.games_export`              | Snapshot bucket with versioning and lifecycle rules                                                                       |
| `aws_lambda_function.ddb_import`          | Imports new Steam games into DynamoDB                                                                                     |
| `aws_lambda_function.ddb_export`          | Exports the full table to S3 as gzipped NDJSON                                                                            |
| `aws_scheduler_schedule.daily_ddb_import` | Triggers import Lambda at **22:00 UTC** daily                                                                             |
| `aws_scheduler_schedule.daily_ddb_export` | Triggers export Lambda at **00:00 UTC** daily                                                                             |
| `aws_ssm_parameter.steam_api_key`         | Pre-created manually — Terraform constructs the ARN from known values and never reads the secret, keeping it out of state |

---

## Import Service — Hexagonal Architecture

The `ddb_import` service is structured around hexagonal (ports & adapters) architecture:

- **Domain** (`domain/game.py`) — `Game` dataclass (`steam_game_id`, `game_title`). No framework dependencies.
- **Ports** (`ports.py`) — Abstract interfaces: `ImportGamesUseCase` (inbound), `GameSource` and `GameRepository` (
  outbound).
- **Service** (`service.py`) — `GameImportService` implements the use case. Fetches all pages from Steam, deduplicates
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

## Local Testing

The `docker/` directory contains a Docker Compose stack for testing Lambda interactions locally without a real AWS
account.

### Start the stack

```bash
cd docker
docker-compose up -d
```

This starts:

| Service    | URL                   | Purpose                                     |
|------------|-----------------------|---------------------------------------------|
| LocalStack | http://localhost:4566 | Mock AWS (DynamoDB, S3, SSM)                |
| WireMock   | http://localhost:8080 | Mock Steam API (stubs baked into the image) |

### Create the Steam API key in LocalStack

Before deploying with Terraform, create the SSM parameter in LocalStack:

```bash
aws --endpoint-url=http://localhost:4566 --region eu-west-2 ssm put-parameter \
  --name "/game-repository/steam-api-key" \
  --value "dummy-local-key" \
  --type SecureString
```

### Deploy infrastructure to LocalStack

Point Terraform at LocalStack by setting AWS endpoint overrides:

```bash
cd terraform

# Configure Terraform to use LocalStack endpoints
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_ENDPOINT_URL_DYNAMODB=http://localhost:4566
export AWS_ENDPOINT_URL_S3=http://localhost:4566
export AWS_ENDPOINT_URL_IAM=http://localhost:4566
export AWS_ENDPOINT_URL_LAMBDA=http://localhost:4566
export AWS_ENDPOINT_URL_SCHEDULER=http://localhost:4566
export AWS_ENDPOINT_URL_STS=http://localhost:4566
export AWS_ENDPOINT_URL_SSM=http://localhost:4566

terraform init
terraform apply -auto-approve
```

> **Note:** LocalStack's EventBridge Scheduler support may be limited. The schedulers will be created but may not
> trigger automatically. Invoke Lambdas manually for testing (see below).

### Invoke Lambdas via AWS CLI

```bash
# Import Lambda
aws --endpoint-url=http://localhost:4566 --region eu-west-2 lambda invoke \
  --function-name ddb-games-import \
  --payload '{}' \
  /dev/stdout

# Export Lambda
aws --endpoint-url=http://localhost:4566 --region eu-west-2 lambda invoke \
  --function-name ddb-games-export \
  --payload '{}' \
  /dev/stdout
```

### Browse data

- **DynamoDB** — scan the table via CLI:
  ```bash
  aws --endpoint-url=http://localhost:4566 --region eu-west-2 dynamodb scan --table-name Games
  ```
- **WireMock admin** — http://localhost:8080/__admin/mappings

---

## Lambda Packaging

Both Lambda zip files are built automatically by Terraform's `archive_file` data source — no manual packaging step is
required.

| Lambda             | Source                                        |
|--------------------|-----------------------------------------------|
| `ddb-games-export` | `terraform/files/ddb_export.py` (single file) |
| `ddb-games-import` | `services/ddb_import/src/` (entire directory) |

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

