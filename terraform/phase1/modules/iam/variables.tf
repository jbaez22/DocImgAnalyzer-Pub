variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
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
  description = "KMS CMK ARN"
  type        = string
}

variable "dynamodb_table_arn" {
  description = "DynamoDB scans table ARN — grants Lambda read/write"
  type        = string
}

variable "reports_bucket_arn" {
  description = "S3 reports bucket ARN — grants Lambda write access"
  type        = string
}

variable "frontend_bucket_arn" {
  description = "S3 frontend bucket ARN — grants CI sync access"
  type        = string
}

variable "artifact_bucket_arn" {
  description = "S3 artifact bucket ARN — grants CI upload access"
  type        = string
}

variable "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — grants CI invalidation permission"
  type        = string
}

variable "state_bucket" {
  description = "S3 bucket name for Terraform remote state (shared backend)"
  type        = string
}

variable "state_lock_table" {
  description = "DynamoDB table name for Terraform state locking (shared backend)"
  type        = string
}
