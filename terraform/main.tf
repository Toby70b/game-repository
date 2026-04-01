resource "aws_s3_bucket" "games_export" {
  bucket = "ddb-games-table-export"
  tags   = var.tags
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
      noncurrent_days           = 5
      newer_noncurrent_versions = 5
    }
  }
}

# ── DynamoDB ────────────────────────────────────────────────────────────────

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
    name            = "gsi_steam_game_id"
    hash_key        = "steam_game_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}

# ── Lambda: daily DynamoDB → S3 export ─────────────────────────────────────

data "archive_file" "ddb_export_lambda" {
  type        = "zip"
  source_file = "${path.module}/files/ddb_export.py"
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
  tags             = var.tags

  environment {
    variables = {
      TABLE_NAME  = aws_dynamodb_table.games.name
      BUCKET_NAME = aws_s3_bucket.games_export.id
      EXPORT_KEY  = "snapshot/games_snapshot.ndjson.gz"
    }
  }
}

# ── EventBridge Scheduler: trigger Lambda daily at 02:00 UTC ───────────────

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

  schedule_expression          = "cron(0 2 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ddb_export.arn
    role_arn = aws_iam_role.ddb_export_scheduler_role.arn
  }
}