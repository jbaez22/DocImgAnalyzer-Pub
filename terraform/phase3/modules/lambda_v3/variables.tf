variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "lambda_exec_role_arn" {
  description = "IAM role ARN for Lambda v3 execution"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
}

# ── Phase 2 dependencies (passed in from remote state) ───────────────────────

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID (Phase 2)"
  type        = string
}

variable "cognito_app_client_id" {
  description = "Cognito App Client ID (Phase 2)"
  type        = string
}

variable "phase2_sqs_queue_url" {
  description = "Phase 2 SQS scan queue URL (Lambda v3 enqueues deep scans)"
  type        = string
}

variable "phase2_ecs_cluster_name" {
  description = "Phase 2 ECS cluster name (for RunTask calls)"
  type        = string
}

variable "phase2_ecs_task_family" {
  description = "Phase 2 ECS task definition family (scanner)"
  type        = string
}

variable "phase2_ecs_subnet_ids" {
  description = "Phase 2 public subnet IDs for Fargate task placement"
  type        = list(string)
}

variable "phase2_ecs_security_group_id" {
  description = "Phase 2 Fargate task security group ID"
  type        = string
}

variable "phase2_dynamodb_v2_table_name" {
  description = "Phase 2 DynamoDB v2 scans table name (Lambda v3 reads scan results)"
  type        = string
}

# ── Phase 3 dependencies ─────────────────────────────────────────────────────

variable "subscriptions_table_name" {
  description = "DynamoDB v3 subscriptions table name"
  type        = string
}

variable "api_keys_table_name" {
  description = "DynamoDB v3 API keys table name"
  type        = string
}

variable "orgs_table_name" {
  description = "DynamoDB v3 orgs table name"
  type        = string
}

variable "stripe_secret_key_arn" {
  description = "Secrets Manager ARN for the Stripe secret key"
  type        = string
}

variable "stripe_secret_manager_path" {
  description = "Secrets Manager path prefix for Stripe secrets (e.g. img-analyzer/dev/stripe)"
  type        = string
}

variable "kms_key_arn" {
  description = "Phase 3 KMS CMK ARN"
  type        = string
}

variable "stripe_pro_price_id" {
  description = "Stripe Price ID for the Pro plan"
  type        = string
}

variable "stripe_enterprise_price_id" {
  description = "Stripe Price ID for the Enterprise plan"
  type        = string
}

variable "frontend_url" {
  description = "Frontend URL for Stripe Checkout success/cancel redirect"
  type        = string
}

# ── API Gateway ───────────────────────────────────────────────────────────────

variable "phase1_api_id" {
  description = "Phase 1 API Gateway ID — v3 routes added to the same gateway"
  type        = string
}

variable "phase2_jwt_authorizer_id" {
  description = "Phase 2 JWT authorizer ID (reused for v3 routes)"
  type        = string
}
