# --- S3 --- #
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "games_export" {
  bucket        = "ddb-games-table-export-${random_id.bucket_suffix.hex}"
  force_destroy = true
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

resource "aws_dynamodb_table" "games" {
  name         = "Games"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "game_id"

  attribute {
    name = "game_id"
    type = "S"
  }

  attribute {
    name = "steam_game_id"
    type = "S"
  }

  global_secondary_index {
    name            = local.steam_gsi_name
    hash_key        = "steam_game_id"
    projection_type = "ALL"
  }

  tags = var.tags
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
        Resource = aws_dynamodb_table.games.arn
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
  function_name    = "ddb-games-export"
  role             = aws_iam_role.ddb_export_lambda_role.arn
  handler          = "ddb_export.handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.ddb_export_lambda.output_base64sha256
  timeout          = 300
  memory_size      = 512
  tags             = var.tags

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.games.name
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
          aws_dynamodb_table.games.arn,
          "${aws_dynamodb_table.games.arn}/index/${local.steam_gsi_name}",
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
  function_name    = "ddb-games-import"
  role             = aws_iam_role.ddb_import_lambda_role.arn
  handler          = "adapters.ddb_import.handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.ddb_import_lambda.output_base64sha256
  timeout          = 900 # Steam app list is large — allow up to 15 min
  memory_size      = 512
  tags             = var.tags

  environment {
    variables = {
      TABLE_NAME          = aws_dynamodb_table.games.name
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