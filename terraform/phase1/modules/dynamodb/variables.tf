variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for DynamoDB table encryption"
  type        = string
}
