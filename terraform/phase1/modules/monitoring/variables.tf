variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "alert_email" {
  description = "Email address for SNS alarm notifications"
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name for alarm dimensions"
  type        = string
}

variable "api_id" {
  description = "API Gateway HTTP API ID for alarm dimensions"
  type        = string
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for alarm dimensions"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS CMK ARN used to encrypt the SNS alerts topic"
  type        = string
}
