# ── Phase 1 remote state (read-only) ─────────────────────────────────────────
data "terraform_remote_state" "phase1" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.phase1_state_key
    region = var.aws_region
  }
}

# ── Phase 2 remote state (read-only) ─────────────────────────────────────────
data "terraform_remote_state" "phase2" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.phase2_state_key
    region = var.aws_region
  }
}

# ── KMS Phase 3 ───────────────────────────────────────────────────────────────
# Dedicated CMK for Phase 3: DynamoDB v3 tables, Secrets Manager (Stripe keys).
module "kms_phase3" {
  source       = "./modules/kms_phase3"
  project_name = var.project_name
  environment  = var.environment
}

# ── DynamoDB v3 ───────────────────────────────────────────────────────────────
# Three new tables: subscriptions, api-keys, orgs.
# Phase 1 and Phase 2 tables are never touched.
module "dynamodb_v3" {
  source       = "./modules/dynamodb_v3"
  project_name = var.project_name
  environment  = var.environment
  kms_key_arn  = module.kms_phase3.key_arn
}

# ── IAM Phase 3 ───────────────────────────────────────────────────────────────
# Four roles: github-actions, lambda-v3-exec, stripe-webhook-exec, eventbridge-scheduler.
module "iam_phase3" {
  source       = "./modules/iam_phase3"
  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  github_org   = var.github_org
  github_repo  = var.github_repo

  kms_key_arn             = module.kms_phase3.key_arn
  subscriptions_table_arn = module.dynamodb_v3.subscriptions_table_arn
  api_keys_table_arn      = module.dynamodb_v3.api_keys_table_arn
  orgs_table_arn          = module.dynamodb_v3.orgs_table_arn

  stripe_secret_key_arn     = module.stripe_webhook.stripe_secret_key_arn
  stripe_webhook_secret_arn = module.stripe_webhook.stripe_webhook_secret_arn

  phase2_sqs_queue_arn         = data.terraform_remote_state.phase2.outputs.sqs_queue_arn
  phase2_dynamodb_v2_table_arn = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${data.terraform_remote_state.phase2.outputs.dynamodb_v2_table_name}"

  cognito_user_pool_arn = data.terraform_remote_state.phase2.outputs.cognito_user_pool_arn

  state_bucket     = var.state_bucket
  state_lock_table = var.state_lock_table
}

data "aws_caller_identity" "current" {}

# ── Stripe Webhook Lambda ─────────────────────────────────────────────────────
# Handles checkout.session.completed, subscription.updated/deleted, invoice events.
# Secrets Manager secrets are created here but values must be set manually.
module "stripe_webhook" {
  source       = "./modules/stripe_webhook"
  project_name = var.project_name
  environment  = var.environment

  kms_key_arn                = module.kms_phase3.key_arn
  stripe_secret_manager_path = var.stripe_secret_manager_path
  stripe_pro_price_id        = var.stripe_pro_price_id
  stripe_enterprise_price_id = var.stripe_enterprise_price_id

  lambda_exec_role_arn     = module.iam_phase3.stripe_webhook_exec_role_arn
  subscriptions_table_name = module.dynamodb_v3.subscriptions_table_name
  log_retention_days       = var.log_retention_days

  phase1_api_id        = data.terraform_remote_state.phase1.outputs.api_gateway_id
  cognito_user_pool_id = data.terraform_remote_state.phase2.outputs.cognito_user_pool_id
}

# ── Lambda v3 ─────────────────────────────────────────────────────────────────
# FastAPI v3 with entitlement middleware, billing/key/org endpoints.
# Routes /api/v3/* added to the same Phase 1 API Gateway with Phase 2 JWT authorizer.
module "lambda_v3" {
  source       = "./modules/lambda_v3"
  project_name = var.project_name
  environment  = var.environment

  lambda_exec_role_arn = module.iam_phase3.lambda_v3_exec_role_arn
  log_retention_days   = var.log_retention_days

  cognito_user_pool_id  = data.terraform_remote_state.phase2.outputs.cognito_user_pool_id
  cognito_app_client_id = data.terraform_remote_state.phase2.outputs.cognito_app_client_id

  phase2_sqs_queue_url          = data.terraform_remote_state.phase2.outputs.sqs_queue_url
  phase2_ecs_cluster_name       = data.terraform_remote_state.phase2.outputs.ecs_cluster_name
  phase2_ecs_task_family        = "${var.project_name}-${var.environment}-scanner"
  phase2_ecs_subnet_ids         = data.terraform_remote_state.phase2.outputs.public_subnet_ids
  phase2_ecs_security_group_id  = data.terraform_remote_state.phase2.outputs.fargate_task_sg_id
  phase2_dynamodb_v2_table_name = data.terraform_remote_state.phase2.outputs.dynamodb_v2_table_name

  subscriptions_table_name = module.dynamodb_v3.subscriptions_table_name
  api_keys_table_name      = module.dynamodb_v3.api_keys_table_name
  orgs_table_name          = module.dynamodb_v3.orgs_table_name

  stripe_secret_key_arn      = module.stripe_webhook.stripe_secret_key_arn
  stripe_secret_manager_path = var.stripe_secret_manager_path
  stripe_pro_price_id        = var.stripe_pro_price_id
  stripe_enterprise_price_id = var.stripe_enterprise_price_id
  kms_key_arn                = module.kms_phase3.key_arn
  frontend_url               = data.terraform_remote_state.phase1.outputs.frontend_url

  phase1_api_id            = data.terraform_remote_state.phase1.outputs.api_gateway_id
  phase2_jwt_authorizer_id = data.terraform_remote_state.phase2.outputs.jwt_authorizer_id
}

# ── EventBridge Re-scan Scheduler ────────────────────────────────────────────
# Nightly trigger at 02:00 UTC — queries subscribed Pro/Enterprise users,
# enqueues re-scan messages to Phase 2 SQS queue.
module "eventbridge" {
  source       = "./modules/eventbridge"
  project_name = var.project_name
  environment  = var.environment

  rescan_schedule_expression = var.rescan_schedule_expression
  scheduler_role_arn         = module.iam_phase3.eventbridge_scheduler_role_arn
  lambda_exec_role_arn       = module.iam_phase3.rescan_trigger_exec_role_arn

  subscriptions_table_name = module.dynamodb_v3.subscriptions_table_name
  scans_v2_table_name      = data.terraform_remote_state.phase2.outputs.dynamodb_v2_table_name
  ecs_cluster              = data.terraform_remote_state.phase2.outputs.ecs_cluster_name
  ecs_task_family          = "${var.project_name}-${var.environment}-scanner"
  ecs_subnet_ids           = join(",", data.terraform_remote_state.phase2.outputs.public_subnet_ids)
  ecs_security_group       = data.terraform_remote_state.phase2.outputs.fargate_task_sg_id
  log_retention_days       = var.log_retention_days
}

# ── Monitoring Phase 3 ────────────────────────────────────────────────────────
module "monitoring_phase3" {
  source       = "./modules/monitoring_phase3"
  project_name = var.project_name
  environment  = var.environment

  lambda_v3_function_name      = module.lambda_v3.function_name
  stripe_webhook_function_name = module.stripe_webhook.function_name
  rescan_trigger_function_name = module.eventbridge.rescan_trigger_function_name
  subscriptions_table_name     = module.dynamodb_v3.subscriptions_table_name
  phase1_sns_topic_arn         = data.terraform_remote_state.phase1.outputs.sns_topic_arn
}
