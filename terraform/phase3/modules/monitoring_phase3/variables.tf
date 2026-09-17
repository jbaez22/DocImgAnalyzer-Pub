variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "lambda_v3_function_name" {
  description = "Lambda v3 function name"
  type        = string
}

variable "stripe_webhook_function_name" {
  description = "Stripe webhook Lambda function name"
  type        = string
}

variable "rescan_trigger_function_name" {
  description = "Re-scan trigger Lambda function name"
  type        = string
}

variable "subscriptions_table_name" {
  description = "DynamoDB subscriptions table name"
  type        = string
}

variable "phase1_sns_topic_arn" {
  description = "Phase 1 SNS topic ARN for alarm notifications"
  type        = string
}
