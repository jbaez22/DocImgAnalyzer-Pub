output "function_name" {
  description = "Stripe webhook Lambda function name"
  value       = aws_lambda_function.webhook.function_name
}

output "function_arn" {
  description = "Stripe webhook Lambda function ARN"
  value       = aws_lambda_function.webhook.arn
}

output "stripe_secret_key_arn" {
  description = "Secrets Manager ARN for the Stripe secret key"
  value       = aws_secretsmanager_secret.stripe_secret_key.arn
}

output "stripe_webhook_secret_arn" {
  description = "Secrets Manager ARN for the Stripe webhook signing secret"
  value       = aws_secretsmanager_secret.stripe_webhook_secret.arn
}
