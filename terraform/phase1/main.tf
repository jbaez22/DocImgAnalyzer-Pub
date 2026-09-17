# ── KMS ───────────────────────────────────────────────────────────────────────
# CMK used by DynamoDB, S3 reports bucket, and Lambda env vars.
module "kms" {
  source       = "./modules/kms"
  project_name = var.project_name
  environment  = var.environment
}

# ── S3 ────────────────────────────────────────────────────────────────────────
# Three buckets: frontend (SSE-S3), reports (KMS), Lambda artifacts (SSE-S3).
module "s3" {
  source       = "./modules/s3"
  project_name = var.project_name
  environment  = var.environment
  kms_key_arn  = module.kms.key_arn
}

# ── DynamoDB ──────────────────────────────────────────────────────────────────
module "dynamodb" {
  source       = "./modules/dynamodb"
  project_name = var.project_name
  environment  = var.environment
  kms_key_arn  = module.kms.key_arn
}

# ── WAF ───────────────────────────────────────────────────────────────────────
# CLOUDFRONT scope WebACL only. REGIONAL WAF not used — AWS does not support
# associating WAFv2 with API Gateway HTTP API $default stages.
module "waf" {
  source       = "./modules/waf"
  project_name = var.project_name
  environment  = var.environment
  rate_limit   = var.waf_rate_limit
}

# ── ACM — API domain ──────────────────────────────────────────────────────────
# Regional certificate for img.craftingnewtech.com (API Gateway regional endpoint).
module "acm_api" {
  source         = "./modules/acm"
  project_name   = var.project_name
  environment    = var.environment
  domain_name    = var.api_domain_name
  hosted_zone_id = var.hosted_zone_id
}

# ── ACM — Frontend domain ─────────────────────────────────────────────────────
# CloudFront requires ACM in us-east-1 — satisfied since that is our region.
module "acm_frontend" {
  source         = "./modules/acm"
  project_name   = var.project_name
  environment    = var.environment
  domain_name    = var.frontend_domain_name
  hosted_zone_id = var.hosted_zone_id
}

# ── CloudFront ────────────────────────────────────────────────────────────────
# CDN for the static frontend. OAC enforced — no public S3 access.
# Also writes the S3 bucket policy granting CloudFront read access.
module "cloudfront" {
  source                      = "./modules/cloudfront"
  project_name                = var.project_name
  environment                 = var.environment
  frontend_bucket_id          = module.s3.frontend_bucket_id
  frontend_bucket_arn         = module.s3.frontend_bucket_arn
  frontend_bucket_domain_name = module.s3.frontend_bucket_domain_name
  waf_arn                     = module.waf.cloudfront_waf_arn
  acm_certificate_arn         = module.acm_frontend.certificate_arn
  domain_name                 = var.frontend_domain_name
}

# ── IAM ───────────────────────────────────────────────────────────────────────
# Lambda execution role + GitHub Actions OIDC CI role.
# References the existing OIDC provider via data source (created by PersonalPorfolio2026).
module "iam" {
  source                     = "./modules/iam"
  project_name               = var.project_name
  environment                = var.environment
  aws_region                 = var.aws_region
  github_org                 = var.github_org
  github_repo                = var.github_repo
  kms_key_arn                = module.kms.key_arn
  dynamodb_table_arn         = module.dynamodb.table_arn
  reports_bucket_arn         = module.s3.reports_bucket_arn
  frontend_bucket_arn        = module.s3.frontend_bucket_arn
  artifact_bucket_arn        = module.s3.artifact_bucket_arn
  cloudfront_distribution_id = module.cloudfront.distribution_id
  state_bucket               = var.state_bucket
  state_lock_table           = var.state_lock_table
}

# ── Lambda ────────────────────────────────────────────────────────────────────
# Python 3.12 FastAPI handler via Mangum. Bootstrapped with a placeholder zip.
# CI pipeline updates function code with the real package after first apply.
module "lambda" {
  source               = "./modules/lambda"
  project_name         = var.project_name
  environment          = var.environment
  lambda_exec_role_arn = module.iam.lambda_exec_role_arn
  reports_bucket_id    = module.s3.reports_bucket_id
  kms_key_arn          = module.kms.key_arn
  dynamodb_table_name  = module.dynamodb.table_name
  allowed_origin       = "https://${var.frontend_domain_name}"
  log_retention_days   = var.log_retention_days
  dynamodb_ttl_days    = var.dynamodb_ttl_days
}

# ── API Gateway ───────────────────────────────────────────────────────────────
# HTTP API v2 with custom domain and Lambda proxy integration.
module "api_gateway" {
  source               = "./modules/api_gateway"
  project_name         = var.project_name
  environment          = var.environment
  lambda_invoke_arn    = module.lambda.alias_invoke_arn
  lambda_function_name = module.lambda.function_name
  acm_certificate_arn  = module.acm_api.certificate_arn
  domain_name          = var.api_domain_name
  allowed_origin       = "https://${var.frontend_domain_name}"
}

# ── Route53 ───────────────────────────────────────────────────────────────────
# A alias records for both domains.
module "route53" {
  source                    = "./modules/route53"
  hosted_zone_id            = var.hosted_zone_id
  api_domain_name           = var.api_domain_name
  api_target_domain         = module.api_gateway.domain_name_target
  api_hosted_zone_id        = module.api_gateway.domain_name_zone_id
  frontend_domain_name      = var.frontend_domain_name
  cloudfront_domain_name    = module.cloudfront.distribution_domain_name
  cloudfront_hosted_zone_id = module.cloudfront.hosted_zone_id
}

# ── Monitoring ────────────────────────────────────────────────────────────────
# SNS topic, CloudWatch alarms, and dashboard.
module "monitoring" {
  source               = "./modules/monitoring"
  project_name         = var.project_name
  environment          = var.environment
  alert_email          = var.alert_email
  lambda_function_name = module.lambda.function_name
  api_id               = module.api_gateway.api_id
  dynamodb_table_name  = module.dynamodb.table_name
  kms_key_arn          = module.kms.key_arn
}
