output "table_arn" {
  value       = aws_dynamodb_table.table.arn
  description = "The ARN of the DynamoDB table"
}

output "table_name" {
  value = aws_dynamodb_table.table.name
  description = "The name of the DynamoDB table"
}

output "stream_arn" {
  value = var.stream_enabled ? aws_dynamodb_table.table.stream_arn : null
  description = "The ARN of the DynamoDB stream, if stream_enabled is true"
}