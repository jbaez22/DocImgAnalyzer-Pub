output "api_endpoint" {
  description = "API custom domain endpoint"
  value       = "https://${var.api_domain_name}"
}

output "frontend_url" {
  description = "Frontend URL"
  value       = "https://${var.frontend_domain_name}"
}

output "lambda_function_name" {
  description = "Lambda function name (used by CI for code updates)"
  value       = module.lambda.function_name
}

output "dynamodb_table_name" {
  description = "DynamoDB scans table name"
  value       = module.dynamodb.table_name
}

output "reports_bucket" {
  description = "S3 bucket for full scan reports"
  value       = module.s3.reports_bucket_id
}

output "frontend_bucket" {
  description = "S3 bucket for static frontend assets"
  value       = module.s3.frontend_bucket_id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (used by CI for cache invalidation)"
  value       = module.cloudfront.distribution_id
}

output "github_actions_role_arn" {
  description = "IAM role ARN assumed by GitHub Actions via OIDC — add as repo secret AWS_ROLE_ARN"
  value       = module.iam.github_actions_role_arn
}

output "api_gateway_id" {
  description = "API Gateway HTTP v2 ID - consumed by Phase 2 to attach /v2/ routes"
  value       = module.api_gateway.api_id
}

output "sns_topic_arn" {
  description = "SNS alerts topic ARN - consumed by Phase 2 monitoring alarms"
  value       = module.monitoring.sns_topic_arn
}
