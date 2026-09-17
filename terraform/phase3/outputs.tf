output "lambda_v3_function_name" {
  description = "Lambda v3 function name (used by CI for code updates)"
  value       = module.lambda_v3.function_name
}

output "stripe_webhook_function_name" {
  description = "Stripe webhook Lambda function name (used by CI for code updates)"
  value       = module.stripe_webhook.function_name
}

output "rescan_trigger_function_name" {
  description = "Re-scan trigger Lambda function name"
  value       = module.eventbridge.rescan_trigger_function_name
}

output "subscriptions_table_name" {
  description = "DynamoDB v3 subscriptions table name"
  value       = module.dynamodb_v3.subscriptions_table_name
}

output "api_keys_table_name" {
  description = "DynamoDB v3 API keys table name"
  value       = module.dynamodb_v3.api_keys_table_name
}

output "orgs_table_name" {
  description = "DynamoDB v3 orgs table name"
  value       = module.dynamodb_v3.orgs_table_name
}

output "github_actions_role_arn" {
  description = "Phase 3 IAM role ARN assumed by GitHub Actions via OIDC"
  value       = module.iam_phase3.github_actions_role_arn
}

output "stripe_secret_key_arn" {
  description = "Secrets Manager ARN for Stripe secret key (set value manually)"
  value       = module.stripe_webhook.stripe_secret_key_arn
}

output "stripe_webhook_secret_arn" {
  description = "Secrets Manager ARN for Stripe webhook signing secret (set value manually)"
  value       = module.stripe_webhook.stripe_webhook_secret_arn
}

output "dashboard_name" {
  description = "Phase 3 CloudWatch dashboard name"
  value       = module.monitoring_phase3.dashboard_name
}

output "stripe_pro_price_id" {
  description = "Stripe Price ID for Pro plan (passed to frontend build)"
  value       = var.stripe_pro_price_id
}

output "stripe_enterprise_price_id" {
  description = "Stripe Price ID for Enterprise plan (passed to frontend build)"
  value       = var.stripe_enterprise_price_id
}
