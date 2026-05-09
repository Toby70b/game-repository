# --- S3 --- #
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "games_export" {
  bucket        = "ddb-games-table-export-${random_id.bucket_suffix.hex}"
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "games_export_versioning" {
  bucket = aws_s3_bucket.games_export.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "games_export_lifecycle" {
  bucket = aws_s3_bucket.games_export.id

  depends_on = [aws_s3_bucket_versioning.games_export_versioning]

  rule {
    id     = "expire-old-snapshots"
    status = "Enabled"

    filter {
      prefix = "snapshot/"
    }

    noncurrent_version_expiration {
      noncurrent_days           = 1
      newer_noncurrent_versions = 5
    }
  }
}

# --- DynamoDB --- #

module "games_table" {
  source = "./modules/dynamodb_table"
  table_name = "Games"
  hash_key   = "game_id"
  stream_enabled = true
  # Only capture new items added to the table
  stream_view_type = "NEW_IMAGE"

  attributes = [
    {
      name = "game_id"
      type = "S"
    },
    {
      name = "steam_game_id"
      type = "S"
    }
  ]

  global_secondary_index = {
    name            = local.steam_gsi_name
    hash_key        = "steam_game_id"
    projection_type = "ALL"
  }

  tags   = var.tags
}

# --- SSM --- #
# The parameter is created out-of-band (see README). Terraform never reads the
# value — only the name and a constructed ARN are used — so the secret is never
# written into Terraform state.
data "aws_caller_identity" "current" {}

locals {
  steam_api_key_param_name = "/game-repository/steam-api-key"
  steam_api_key_param_arn  = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${local.steam_api_key_param_name}"
  steam_gsi_name           = "gsi_steam_game_id"
}

# --- Lambda Export Job --- #

data "archive_file" "ddb_export_lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/ddb_export/ddb_export.py"
  output_path = "${path.module}/files/ddb_export.zip"
}

resource "aws_iam_role" "ddb_export_lambda_role" {
  name = "ddb-export-lambda-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ddb_export_lambda_policy" {
  name = "ddb-export-lambda-policy"
  role = aws_iam_role.ddb_export_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan"]
        Resource = module.games_table.table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.games_export.arn}/snapshot/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_lambda_function" "ddb_export" {
  filename         = data.archive_file.ddb_export_lambda.output_path
  source_code_hash = data.archive_file.ddb_export_lambda.output_base64sha256

  function_name    = "ddb-games-export"
  role             = aws_iam_role.ddb_export_lambda_role.arn
  handler          = "ddb_export.handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512
  tags             = var.tags

  environment {
    variables = {
      TABLE_NAME         = module.games_table.table_name
      EXPORT_BUCKET_NAME = aws_s3_bucket.games_export.id
      EXPORT_KEY         = "snapshot/games_snapshot.json.gz"
    }
  }
}

resource "aws_iam_role" "ddb_export_scheduler_role" {
  name = "ddb-export-scheduler-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ddb_export_scheduler_policy" {
  name = "ddb-export-scheduler-policy"
  role = aws_iam_role.ddb_export_scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.ddb_export.arn
    }]
  })
}

resource "aws_scheduler_schedule" "daily_ddb_export" {
  name       = "daily-ddb-export"
  group_name = "default"

  schedule_expression          = "cron(0 0 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ddb_export.arn
    role_arn = aws_iam_role.ddb_export_scheduler_role.arn
  }
}

# --- Lambda Import Job --- #

data "archive_file" "ddb_import_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/ddb_import/src"
  output_path = "${path.module}/files/ddb_import.zip"
}

resource "aws_iam_role" "ddb_import_lambda_role" {
  name = "ddb-import-lambda-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ddb_import_lambda_policy" {
  name = "ddb-import-lambda-policy"
  role = aws_iam_role.ddb_import_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:BatchWriteItem",
        ]
        Resource = [
          module.games_table.table_arn,
          "${module.games_table.table_arn}/index/${local.steam_gsi_name}",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = local.steam_api_key_param_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_lambda_function" "ddb_import" {
  filename         = data.archive_file.ddb_import_lambda.output_path
  source_code_hash = data.archive_file.ddb_import_lambda.output_base64sha256

  function_name    = "ddb-games-import"
  role             = aws_iam_role.ddb_import_lambda_role.arn
  handler          = "adapters.ddb_import.handler"
  runtime          = "python3.12"
  timeout          = 900 # Steam app list is large — allow up to 15 min
  memory_size      = 512
  tags             = var.tags

  environment {
    variables = {
      TABLE_NAME          = module.games_table.table_name
      STEAM_GAME_ID_INDEX = local.steam_gsi_name
      STEAM_API_KEY_PARAM = local.steam_api_key_param_name
      STEAM_API_BASE_URL  = var.steam_api_base_url
    }
  }
}

resource "aws_iam_role" "ddb_import_scheduler_role" {
  name = "ddb-import-scheduler-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ddb_import_scheduler_policy" {
  name = "ddb-import-scheduler-policy"
  role = aws_iam_role.ddb_import_scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.ddb_import.arn
    }]
  })
}

resource "aws_scheduler_schedule" "daily_ddb_import" {
  name       = "daily-ddb-import"
  group_name = "default"

  schedule_expression          = "cron(0 22 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ddb_import.arn
    role_arn = aws_iam_role.ddb_import_scheduler_role.arn
  }
}

# --- SNS --- #
module "new_game_items" {
  source = "./modules/sns_topic"
  topic_name = "new-game-items"
  tags = var.tags
}

# --- Lambda (publish to SNS) --- #
data "archive_file" "ddb_new_game_item_publisher_lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/ddb_stream_publish/ddb_stream_publish.py"
  output_path = "${path.module}/files/ddb_stream_publish.zip"
}

resource "aws_lambda_function" "new_game_item_publisher" {
    filename         = data.archive_file.ddb_new_game_item_publisher_lambda.output_path
    source_code_hash = data.archive_file.ddb_new_game_item_publisher_lambda.output_base64sha256

    function_name    = "new-game-item-publisher"
    role             = aws_iam_role.new_game_item_publisher.arn
    handler          = "ddb_stream_publish.lambda_handler"
    runtime          = "python3.12"
    timeout          = 30
    memory_size      = 128
    tags             = var.tags

    environment {
        variables = {
          TOPIC_ARN = module.new_game_items.topic_arn
        }
    }
}

resource "aws_iam_role" "new_game_item_publisher" {
  name = "new-game-item-publisher-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "new_game_item_publisher" {
  name = "new-game-item-publisher-policy"

  role   = aws_iam_role.new_game_item_publisher.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = module.new_game_items.topic_arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:DescribeStream",
          "dynamodb:ListStreams"
        ]
        Resource = module.games_table.stream_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_lambda_event_source_mapping" "new_game_item_stream" {
  event_source_arn  = module.games_table.stream_arn
  function_name     = aws_lambda_function.new_game_item_publisher.arn
  starting_position = "TRIM_HORIZON" # process all existing stream records on deployment

  # Batch settings -  need to consider initial setup scenario
  batch_size                         = 100
  maximum_batching_window_in_seconds = 5
  # Default seeing - Reduce throttle errors during bulk load
  parallelization_factor = 1

  tags = var.tags
}

