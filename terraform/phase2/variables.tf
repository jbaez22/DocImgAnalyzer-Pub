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

# ── Phase 1 remote state (read-only) ─────────────────────────────────────────

variable "phase1_state_key" {
  description = "S3 key of the Phase 1 Terraform state for this environment (read-only remote_state data source)"
  type        = string
}

# ── VPC / Networking ──────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block for the Phase 2 VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet — hosts NAT Gateway and Gateway Endpoints"
  type        = string
  default     = "10.0.10.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet — Fargate tasks run here, routed via NAT Gateway"
  type        = string
  default     = "10.0.20.0/24"
}

variable "availability_zone" {
  description = "Availability zone for the public subnet"
  type        = string
  default     = "us-east-1a"
}

variable "fargate_use_private_subnet" {
  description = <<-EOT
    Whether Fargate scanner tasks (both the EventBridge Pipe launch path and
    Lambda v2's direct RunTask launch path) run in the private subnet (NAT
    Gateway egress) or the public subnet (public IP egress). Both paths must
    agree -- this is the single source of truth for both, added 2026-07-16
    after Lambda v2's env var and the Pipe's CI-managed network config were
    found independently hardcoded to private_subnet_ids, which broke for
    any environment that hadn't actually done the NAT Gateway migration.
  EOT
  type        = bool
  default     = true
}

# ── Cognito ───────────────────────────────────────────────────────────────────

variable "cognito_domain_prefix" {
  description = "Prefix for the Cognito-hosted UI domain ({prefix}.auth.us-east-1.amazoncognito.com)"
  type        = string
}

# ── SQS ──────────────────────────────────────────────────────────────────────

variable "sqs_visibility_timeout_seconds" {
  description = "SQS message visibility timeout — should be >= Fargate task max duration"
  type        = number
  default     = 360
}

variable "sqs_message_retention_seconds" {
  description = "How long SQS retains unprocessed messages"
  type        = number
  default     = 86400
}

variable "sqs_max_receive_count" {
  description = "Number of delivery attempts before moving to DLQ"
  type        = number
  default     = 3
}

# ── ECS Fargate ───────────────────────────────────────────────────────────────

variable "fargate_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "fargate_memory" {
  description = "Fargate task memory in MB"
  type        = number
  default     = 512
}

# ── DynamoDB v2 ───────────────────────────────────────────────────────────────

variable "free_tier_ttl_days" {
  description = "Days before unauthenticated scan records expire (0 = disabled)"
  type        = number
  default     = 30
}

# ── ECR ───────────────────────────────────────────────────────────────────────

variable "ecr_image_retention_count" {
  description = "Maximum number of scanner images to keep in ECR"
  type        = number
  default     = 10
}

