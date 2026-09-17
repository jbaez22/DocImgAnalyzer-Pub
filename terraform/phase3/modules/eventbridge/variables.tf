variable "project_name" {
  description = "Short name used to prefix all resource names"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "rescan_schedule_expression" {
  description = "EventBridge Scheduler cron expression for the nightly re-scan trigger"
  type        = string
}

variable "scheduler_role_arn" {
  description = "IAM role ARN for EventBridge Scheduler"
  type        = string
}

variable "lambda_exec_role_arn" {
  description = "IAM role ARN for the re-scan trigger Lambda"
  type        = string
}

variable "subscriptions_table_name" {
  description = "DynamoDB v3 subscriptions table name"
  type        = string
}

variable "scans_v2_table_name" {
  description = "DynamoDB phase2 scans-v2 table name (read recent image scans)"
  type        = string
}

variable "ecs_cluster" {
  description = "Phase 2 ECS cluster name"
  type        = string
}

variable "ecs_task_family" {
  description = "Phase 2 ECS task definition family name (scanner)"
  type        = string
}

variable "ecs_subnet_ids" {
  description = "Comma-separated Phase 2 public subnet IDs for Fargate tasks"
  type        = string
}

variable "ecs_security_group" {
  description = "Phase 2 Fargate task security group ID"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
}
