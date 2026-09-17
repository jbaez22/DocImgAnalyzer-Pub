output "table_name" {
  value = aws_dynamodb_table.scans.name
}

output "table_arn" {
  value = aws_dynamodb_table.scans.arn
}
