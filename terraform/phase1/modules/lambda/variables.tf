variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "lambda_exec_role_arn" {
  description = "IAM execution role ARN for the Lambda function"
  type        = string
}

variable "reports_bucket_id" {
  description = "S3 reports bucket name — passed to Lambda as env var"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used to encrypt Lambda environment variables"
  type        = string
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name — passed to Lambda as env var"
  type        = string
}

variable "allowed_origin" {
  description = "CORS allowed origin — passed to Lambda as env var"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 14
}

variable "dynamodb_ttl_days" {
  description = "Days until DynamoDB scan records expire — passed to Lambda as env var"
  type        = number
  default     = 90
}
