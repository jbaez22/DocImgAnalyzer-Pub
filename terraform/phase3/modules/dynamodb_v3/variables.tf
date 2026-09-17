variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "kms_key_arn" {
  description = "Phase 3 KMS CMK ARN for DynamoDB server-side encryption"
  type        = string
}
