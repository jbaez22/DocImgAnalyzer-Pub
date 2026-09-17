output "cognito_user_pool_id" {
  description = "Cognito User Pool ID — needed for frontend Amplify config"
  value       = module.cognito.user_pool_id
}

output "cognito_app_client_id" {
  description = "Cognito App Client ID — needed for frontend Amplify config"
  value       = module.cognito.app_client_id
}

output "cognito_domain" {
  description = "Cognito hosted UI domain"
  value       = module.cognito.domain
}

output "sqs_queue_url" {
  description = "SQS scan queue URL"
  value       = module.sqs.queue_url
}

output "sqs_queue_arn" {
  description = "SQS scan queue ARN — used by Phase 3 IAM policies"
  value       = module.sqs.queue_arn
}

output "sqs_dlq_url" {
  description = "SQS dead-letter queue URL"
  value       = module.sqs.dlq_url
}

output "ecr_repository_url" {
  description = "ECR repository URL for the scanner image (used by CI to push)"
  value       = module.ecr.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "lambda_v2_function_name" {
  description = "Lambda v2 function name (used by CI for code updates)"
  value       = module.lambda_v2.function_name
}

output "dynamodb_v2_table_name" {
  description = "DynamoDB v2 scans table name"
  value       = module.dynamodb_v2.table_name
}

output "reports_bucket" {
  description = "S3 bucket for CVE reports"
  value       = module.s3_phase2.reports_bucket_id
}

output "sbom_bucket" {
  description = "S3 bucket for SBOM outputs"
  value       = module.s3_phase2.sbom_bucket_id
}

output "github_actions_role_arn" {
  description = "Phase 2 IAM role ARN assumed by GitHub Actions via OIDC"
  value       = module.iam_phase2.github_actions_role_arn
}

output "github_actions_plan_role_arn" {
  description = "Phase 2 read-only IAM role ARN assumed by GitHub Actions for PR-time terraform plan only"
  value       = module.iam_phase2.github_actions_plan_role_arn
}

output "vpc_id" {
  description = "Phase 2 VPC ID"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (NAT Gateway lives here)"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs for Fargate tasks (used by pipeline to update Pipe)"
  value       = module.vpc.private_subnet_ids
}

output "fargate_subnet_ids" {
  description = <<-EOT
    Subnet IDs Fargate scanner tasks actually run in, per
    var.fargate_use_private_subnet -- the pipeline's "Update ECS task
    definition and Pipe" step should read this, not private_subnet_ids
    directly, since that output is unconditionally populated even for
    environments that have not done the NAT Gateway migration.
  EOT
  value       = local.fargate_subnet_ids
}

output "fargate_assign_public_ip" {
  description = "ENABLED or DISABLED -- must accompany fargate_subnet_ids together, never used alone"
  value       = local.fargate_assign_public_ip
}

output "fargate_task_sg_id" {
  description = "Fargate task security group ID (used by pipeline to update Pipe)"
  value       = module.vpc.fargate_task_sg_id
}

output "pipe_name" {
  description = "EventBridge Pipe name (used by pipeline to update task definition)"
  value       = "${var.project_name}-${var.environment}-scan-trigger"
}

output "jwt_authorizer_id" {
  description = "Cognito JWT authorizer ID — reused by Phase 3 v3 routes on the same API Gateway"
  value       = module.lambda_v2.authorizer_id
}

output "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN — needed by Phase 3 IAM for AdminUpdateUserAttributes"
  value       = module.cognito.user_pool_arn
}
