variable "project_name" { type = string }
variable "environment" { type = string }
variable "aws_region" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "assign_public_ip" {
  type        = string
  description = "ENABLED or DISABLED -- must match whichever subnet private_subnet_ids actually holds"
}
variable "fargate_task_sg_id" { type = string }
variable "fargate_cpu" { type = number }
variable "fargate_memory" { type = number }
variable "scanner_image" {
  type        = string
  description = "Full Docker image reference for the scanner (e.g. dockjb24/img-analyzer-scanner:latest)"
}
variable "task_role_arn" { type = string }
variable "execution_role_arn" { type = string }
variable "sqs_queue_arn" { type = string }
variable "dynamodb_v2_table_name" { type = string }
variable "reports_bucket_id" { type = string }
variable "sbom_bucket_id" { type = string }
variable "log_retention_days" { type = number }
