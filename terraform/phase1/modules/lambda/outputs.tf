output "function_arn" {
  value = aws_lambda_function.api.arn
}

output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "invoke_arn" {
  description = "Lambda function invocation ARN (unqualified)"
  value       = aws_lambda_function.api.invoke_arn
}

output "alias_arn" {
  description = "Live alias ARN"
  value       = aws_lambda_alias.live.arn
}

output "alias_invoke_arn" {
  description = "Live alias invocation ARN — used by API Gateway integration"
  value       = aws_lambda_alias.live.invoke_arn
}
