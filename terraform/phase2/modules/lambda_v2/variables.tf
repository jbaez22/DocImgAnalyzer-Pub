variable "project_name" { type = string }
variable "environment" { type = string }
variable "lambda_exec_role_arn" { type = string }
variable "cognito_user_pool_id" { type = string }
variable "cognito_client_id" { type = string }
variable "sqs_queue_url" { type = string }
variable "dynamodb_v2_table_name" { type = string }
variable "reports_bucket_id" { type = string }
variable "sbom_bucket_id" { type = string }
variable "log_retention_days" { type = number }
variable "phase1_api_id" { type = string }
variable "ecs_cluster_name" { type = string }
variable "ecs_task_definition_family" { type = string }
variable "ecs_subnet_ids" { type = list(string) }
variable "ecs_assign_public_ip" {
  type        = string
  description = "ENABLED or DISABLED -- must match whichever subnet ecs_subnet_ids actually holds"
}
variable "ecs_security_group_id" { type = string }
