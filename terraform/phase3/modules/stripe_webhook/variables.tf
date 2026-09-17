variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "kms_key_arn" {
  description = "Phase 3 KMS CMK ARN for Secrets Manager encryption"
  type        = string
}

variable "stripe_secret_manager_path" {
  description = "Secrets Manager path prefix for Stripe secrets"
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

variable "lambda_exec_role_arn" {
  description = "IAM role ARN for the Stripe webhook Lambda"
  type        = string
}

variable "subscriptions_table_name" {
  description = "DynamoDB subscriptions table name"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
}

variable "phase1_api_id" {
  description = "Phase 1 API Gateway ID — webhook route added to the same gateway"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID (from Phase 2) — for updating user custom attributes"
  type        = string
}
