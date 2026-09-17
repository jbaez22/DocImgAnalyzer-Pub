variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "github_org" {
  description = "GitHub organisation or username"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "kms_key_arn" {
  description = "Phase 3 KMS CMK ARN"
  type        = string
}

variable "subscriptions_table_arn" {
  description = "DynamoDB subscriptions table ARN"
  type        = string
}

variable "api_keys_table_arn" {
  description = "DynamoDB API keys table ARN"
  type        = string
}

variable "orgs_table_arn" {
  description = "DynamoDB orgs table ARN"
  type        = string
}

variable "stripe_secret_key_arn" {
  description = "Secrets Manager ARN for the Stripe secret key"
  type        = string
}

variable "stripe_webhook_secret_arn" {
  description = "Secrets Manager ARN for the Stripe webhook signing secret"
  type        = string
}

variable "phase2_sqs_queue_arn" {
  description = "Phase 2 SQS queue ARN (Lambda v3 and EventBridge send to this queue)"
  type        = string
}

variable "phase2_dynamodb_v2_table_arn" {
  description = "Phase 2 DynamoDB v2 scans table ARN (Lambda v3 reads scan results)"
  type        = string
}

variable "state_bucket" {
  description = "Terraform state S3 bucket name"
  type        = string
}

variable "state_lock_table" {
  description = "Terraform state lock DynamoDB table name"
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "Phase 2 Cognito User Pool ARN (for updating user custom attributes)"
  type        = string
}
