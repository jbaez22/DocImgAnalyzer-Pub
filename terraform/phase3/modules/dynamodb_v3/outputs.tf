output "subscriptions_table_name" {
  description = "DynamoDB subscriptions table name"
  value       = aws_dynamodb_table.subscriptions.name
}

output "subscriptions_table_arn" {
  description = "DynamoDB subscriptions table ARN"
  value       = aws_dynamodb_table.subscriptions.arn
}

output "api_keys_table_name" {
  description = "DynamoDB API keys table name"
  value       = aws_dynamodb_table.api_keys.name
}

output "api_keys_table_arn" {
  description = "DynamoDB API keys table ARN"
  value       = aws_dynamodb_table.api_keys.arn
}

output "orgs_table_name" {
  description = "DynamoDB orgs table name"
  value       = aws_dynamodb_table.orgs.name
}

output "orgs_table_arn" {
  description = "DynamoDB orgs table ARN"
  value       = aws_dynamodb_table.orgs.arn
}
