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

variable "state_bucket" {
  description = "S3 bucket name for Terraform remote state (shared backend)"
  type        = string
}

variable "state_lock_table" {
  description = "DynamoDB table name for Terraform state locking (shared backend)"
  type        = string
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications via SNS"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 14
}

# ── Remote state keys ─────────────────────────────────────────────────────────

variable "phase1_state_key" {
  description = "S3 key of the Phase 1 Terraform state for this environment (read-only)"
  type        = string
}

variable "phase2_state_key" {
  description = "S3 key of the Phase 2 Terraform state for this environment (read-only)"
  type        = string
}

# ── Stripe ────────────────────────────────────────────────────────────────────

variable "stripe_pro_price_id" {
  description = "Stripe Price ID for the Pro plan ($19/month)"
  type        = string
}

variable "stripe_enterprise_price_id" {
  description = "Stripe Price ID for the Enterprise plan ($99/month)"
  type        = string
}

variable "stripe_secret_manager_path" {
  description = "Secrets Manager path prefix for Stripe secrets (e.g. img-analyzer/dev/stripe)"
  type        = string
}

# ── DynamoDB v3 ───────────────────────────────────────────────────────────────

variable "free_tier_ttl_days" {
  description = "Days before free-tier scan records expire in the subscriptions table (0 = disabled)"
  type        = number
  default     = 30
}

# ── Lambda v3 / Stripe webhook ────────────────────────────────────────────────

variable "lambda_v3_image_tag" {
  description = "ECR image tag for Lambda v3 (managed by CI, ignored in Terraform lifecycle)"
  type        = string
  default     = "latest"
}

variable "scanner_image_tag" {
  description = "ECR image tag for the Fargate scanner container (read from Phase 2 state)"
  type        = string
  default     = "latest"
}

# ── EventBridge re-scanning ───────────────────────────────────────────────────

variable "rescan_schedule_expression" {
  description = "EventBridge Scheduler cron expression for the nightly re-scan trigger"
  type        = string
  default     = "cron(0 2 * * ? *)"
}
