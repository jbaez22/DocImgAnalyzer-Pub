# ── Phase 1 remote state (read-only) ─────────────────────────────────────────
# Phase 2 reads Phase 1 outputs (API Gateway ID, Lambda name, etc.) via remote state.
# This is strictly read-only — Phase 2 apply never modifies Phase 1 state.
data "terraform_remote_state" "phase1" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.phase1_state_key
    region = var.aws_region
  }
}

# ── KMS Phase 2 ───────────────────────────────────────────────────────────────
# Dedicated CMK removed 2026-07-16 per Phase3DeploymentPlanPoC.md item 9 --
# DynamoDB v2, SQS, and S3 Phase 2 buckets now use AWS-owned keys (free).

# ── VPC ───────────────────────────────────────────────────────────────────────
# Public subnet (NAT Gateway + IGW) always created. Private subnet (Fargate
# tasks) + NAT Gateway + EIP only created when fargate_use_private_subnet is
# true -- see var.fargate_use_private_subnet.
# S3 and DynamoDB route through free Gateway Endpoints (both subnets, when present).
module "vpc" {
  source                = "./modules/vpc"
  project_name          = var.project_name
  environment           = var.environment
  vpc_cidr              = var.vpc_cidr
  public_subnet_cidr    = var.public_subnet_cidr
  private_subnet_cidr   = var.private_subnet_cidr
  availability_zone     = var.availability_zone
  create_private_subnet = var.fargate_use_private_subnet
}

# Single source of truth for which subnet Fargate scanner tasks run in --
# both the EventBridge Pipe's network config (module.ecs) and Lambda v2's
# direct RunTask launch path (module.lambda_v2) must agree. See
# var.fargate_use_private_subnet for why this exists.
locals {
  fargate_subnet_ids = var.fargate_use_private_subnet ? module.vpc.private_subnet_ids : module.vpc.public_subnet_ids
  # Private subnet tasks reach the internet via NAT Gateway (no public IP
  # needed/wanted); public subnet tasks need a public IP to reach the
  # internet via IGW at all, or they get zero egress (ECR/Docker Hub/CW
  # Logs all become unreachable). Must track fargate_subnet_ids exactly.
  fargate_assign_public_ip = var.fargate_use_private_subnet ? "DISABLED" : "ENABLED"
}

# ── Cognito ───────────────────────────────────────────────────────────────────
# User Pool with email+password auth, email verification, password policy.
# App client configured for SPA (no client secret, PKCE flow).
module "cognito" {
  source                = "./modules/cognito"
  project_name          = var.project_name
  environment           = var.environment
  cognito_domain_prefix = var.cognito_domain_prefix
  frontend_url          = data.terraform_remote_state.phase1.outputs.frontend_url
}

# ── SQS ───────────────────────────────────────────────────────────────────────
# Scan job queue + DLQ. Encrypted with SSE-SQS (AWS-owned key, free) --
# CMK removed 2026-07-16 (see the KMS Phase 2 note above).
# visibility_timeout must be >= Fargate task max run duration.
module "sqs" {
  source                     = "./modules/sqs"
  project_name               = var.project_name
  environment                = var.environment
  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds
  message_retention_seconds  = var.sqs_message_retention_seconds
  max_receive_count          = var.sqs_max_receive_count
}

# ── DynamoDB v2 ───────────────────────────────────────────────────────────────
# New table for Phase 2 scans — Phase 1 table is never touched.
# GSI on user_id enables efficient authenticated user history queries.
module "dynamodb_v2" {
  source             = "./modules/dynamodb_v2"
  project_name       = var.project_name
  environment        = var.environment
  free_tier_ttl_days = var.free_tier_ttl_days
}

# ── S3 Phase 2 ────────────────────────────────────────────────────────────────
# CVE reports bucket + SBOM bucket — both encrypted with SSE-S3 (AES256,
# AWS-owned key, free) -- CMK removed 2026-07-16 (see the KMS Phase 2 note above).
module "s3_phase2" {
  source          = "./modules/s3_phase2"
  project_name    = var.project_name
  environment     = var.environment
  frontend_origin = data.terraform_remote_state.phase1.outputs.frontend_url
}

# ── ECR ───────────────────────────────────────────────────────────────────────
# Repository for the Trivy + Syft scanner container image.
module "ecr" {
  source                = "./modules/ecr"
  project_name          = var.project_name
  environment           = var.environment
  image_retention_count = var.ecr_image_retention_count
}

# ── IAM Phase 2 ───────────────────────────────────────────────────────────────
# Three roles: github-actions (CI/CD), lambda-v2 (execution), fargate-task (scanner).
# No role has access to Phase 1 DynamoDB table or Phase 1 S3 buckets.
module "iam_phase2" {
  source                = "./modules/iam_phase2"
  project_name          = var.project_name
  environment           = var.environment
  aws_region            = var.aws_region
  github_org            = var.github_org
  github_repo           = var.github_repo
  dynamodb_v2_table_arn = module.dynamodb_v2.table_arn
  sqs_queue_arn         = module.sqs.queue_arn
  # String-interpolated, not module.s3_phase2 outputs -- keeps this module's
  # dependency graph decoupled from s3_phase2 so `-target=module.iam_phase2`
  # only ever touches IAM. See 2026-07-16 incident: -target on this module
  # transitively pulled in module.s3_phase2's bucket resources via a
  # module-output dependency, surfacing an unrelated pre-existing taint on
  # the report buckets during what was meant to be an IAM-only apply.
  reports_bucket_arn = "arn:aws:s3:::${var.project_name}-${var.environment}-cve-reports"
  sbom_bucket_arn    = "arn:aws:s3:::${var.project_name}-${var.environment}-sbom-reports"
  state_bucket       = var.state_bucket
  state_lock_table   = var.state_lock_table
}

# ── ECS Fargate ───────────────────────────────────────────────────────────────
# Fargate tasks run in the private subnet (outbound via NAT Gateway) or the
# public subnet (outbound via IGW, needs a public IP), per
# var.fargate_use_private_subnet -- see local.fargate_subnet_ids above.
# This enables Trivy to pull target images (nginx, node, etc.) from Docker Hub.
# The pipeline updates the task definition image on every deploy via register-task-definition.
module "ecs" {
  source                 = "./modules/ecs"
  project_name           = var.project_name
  environment            = var.environment
  aws_region             = var.aws_region
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = local.fargate_subnet_ids
  assign_public_ip       = local.fargate_assign_public_ip
  fargate_task_sg_id     = module.vpc.fargate_task_sg_id
  fargate_cpu            = var.fargate_cpu
  fargate_memory         = var.fargate_memory
  scanner_image          = "${module.ecr.repository_url}:latest"
  task_role_arn          = module.iam_phase2.fargate_task_role_arn
  execution_role_arn     = module.iam_phase2.fargate_execution_role_arn
  sqs_queue_arn          = module.sqs.queue_arn
  dynamodb_v2_table_name = module.dynamodb_v2.table_name
  reports_bucket_id      = module.s3_phase2.reports_bucket_id
  sbom_bucket_id         = module.s3_phase2.sbom_bucket_id
  log_retention_days     = var.log_retention_days
}

# ── Lambda v2 ─────────────────────────────────────────────────────────────────
# FastAPI v2 handler — routes /api/v2/* through API Gateway JWT authorizer.
# Phase 1 Lambda (backend/app/) is never modified.
module "lambda_v2" {
  source                 = "./modules/lambda_v2"
  project_name           = var.project_name
  environment            = var.environment
  lambda_exec_role_arn   = module.iam_phase2.lambda_v2_exec_role_arn
  cognito_user_pool_id   = module.cognito.user_pool_id
  cognito_client_id      = module.cognito.app_client_id
  sqs_queue_url          = module.sqs.queue_url
  dynamodb_v2_table_name = module.dynamodb_v2.table_name
  reports_bucket_id      = module.s3_phase2.reports_bucket_id
  sbom_bucket_id         = module.s3_phase2.sbom_bucket_id
  log_retention_days     = var.log_retention_days

  # ECS Fargate — Lambda triggers scanner tasks directly via RunTask
  ecs_cluster_name           = module.ecs.cluster_name
  ecs_task_definition_family = "${var.project_name}-${var.environment}-scanner"
  ecs_subnet_ids             = local.fargate_subnet_ids
  ecs_assign_public_ip       = local.fargate_assign_public_ip
  ecs_security_group_id      = module.vpc.fargate_task_sg_id

  # Phase 1 API Gateway ID — Phase 2 routes are added to the same gateway
  phase1_api_id = data.terraform_remote_state.phase1.outputs.api_gateway_id
}

# ── Monitoring Phase 2 ────────────────────────────────────────────────────────
# Separate CloudWatch dashboard + alarms for Phase 2 resources.
# Routes to the same SNS topic created in Phase 1.
module "monitoring_phase2" {
  source                  = "./modules/monitoring_phase2"
  project_name            = var.project_name
  environment             = var.environment
  lambda_v2_function_name = module.lambda_v2.function_name
  sqs_queue_name          = module.sqs.queue_name
  sqs_dlq_name            = module.sqs.dlq_name
  ecs_cluster_name        = module.ecs.cluster_name
  ecs_service_name        = module.ecs.service_name
  cognito_user_pool_id    = module.cognito.user_pool_id
  phase1_sns_topic_arn    = data.terraform_remote_state.phase1.outputs.sns_topic_arn
}
