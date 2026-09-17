output "function_name" {
  description = "Lambda v3 function name"
  value       = aws_lambda_function.v3.function_name
}

output "function_arn" {
  description = "Lambda v3 function ARN"
  value       = aws_lambda_function.v3.arn
}

output "alias_arn" {
  description = "Lambda v3 alias ARN"
  value       = aws_lambda_alias.v3.arn
}
