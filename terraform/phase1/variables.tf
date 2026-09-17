variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be 'dev' or 'prod'."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
}

variable "owner" {
  description = "Owner tag applied to all resources"
  type        = string
}

variable "github_org" {
  description = "GitHub organisation or username that owns the repo"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "api_domain_name" {
  description = "Custom domain for the API endpoint"
  type        = string
}

variable "frontend_domain_name" {
  description = "Custom domain for the frontend"
  type        = string
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID for the parent domain (craftingnewtech.com)"
  type        = string
}

variable "alert_email" {
  description = "Email address to receive CloudWatch alarm notifications via SNS"
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

variable "waf_rate_limit" {
  description = "Max requests per 5-minute window per IP before WAF blocks"
  type        = number
  default     = 1000
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 14
}

variable "dynamodb_ttl_days" {
  description = "Days before DynamoDB scan records auto-expire (written by Lambda as epoch TTL)"
  type        = number
  default     = 90
}
