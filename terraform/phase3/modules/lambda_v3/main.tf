data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_log_group" "lambda_v3" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-api-v3"
  retention_in_days = var.log_retention_days
}

data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = "# placeholder — replaced by CI pipeline deploy"
    filename = "main.py"
  }
}

resource "aws_lambda_function" "v3" {
  function_name    = "${var.project_name}-${var.environment}-api-v3"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.12"
  handler          = "v3.main.handler"
  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256
  timeout          = 30
  memory_size      = 512

  environment {
    variables = {
      ENVIRONMENT                = var.environment
      COGNITO_USER_POOL_ID       = var.cognito_user_pool_id
      COGNITO_APP_CLIENT_ID      = var.cognito_app_client_id
      SUBSCRIPTIONS_TABLE        = var.subscriptions_table_name
      API_KEYS_TABLE             = var.api_keys_table_name
      ORGS_TABLE                 = var.orgs_table_name
      DYNAMODB_V2_TABLE          = var.phase2_dynamodb_v2_table_name
      SQS_QUEUE_URL              = var.phase2_sqs_queue_url
      ECS_CLUSTER_NAME           = var.phase2_ecs_cluster_name
      ECS_TASK_FAMILY            = var.phase2_ecs_task_family
      ECS_SUBNET_IDS             = join(",", var.phase2_ecs_subnet_ids)
      ECS_SECURITY_GROUP_ID      = var.phase2_ecs_security_group_id
      STRIPE_SECRET_ARN          = var.stripe_secret_key_arn
      STRIPE_SECRET_MANAGER_PATH = var.stripe_secret_manager_path
      STRIPE_PRO_PRICE_ID        = var.stripe_pro_price_id
      STRIPE_ENTERPRISE_PRICE_ID = var.stripe_enterprise_price_id
      FRONTEND_URL               = var.frontend_url
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  depends_on = [aws_cloudwatch_log_group.lambda_v3]
}

resource "aws_lambda_alias" "v3" {
  name             = "v3"
  function_name    = aws_lambda_function.v3.function_name
  function_version = "$LATEST"

  lifecycle {
    ignore_changes = [function_version]
  }
}

# ── API Gateway v3 routes ─────────────────────────────────────────────────────

resource "aws_apigatewayv2_integration" "v3" {
  api_id                 = var.phase1_api_id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.v3.invoke_arn
  payload_format_version = "2.0"
}

locals {
  # Routes requiring Cognito JWT — API Gateway validates the Bearer token before Lambda is invoked.
  v3_jwt_routes = [
    "GET /api/v3/results/{scan_id}",
    "GET /api/v3/scans",
    "GET /api/v3/scans/trend",
    "POST /api/v3/billing/checkout",
    "POST /api/v3/billing/portal",
    "GET /api/v3/billing/status",
    "POST /api/v3/keys",
    "GET /api/v3/keys",
    "DELETE /api/v3/keys/{key_id}",
    "POST /api/v3/orgs",
    "GET /api/v3/orgs/me",
    "POST /api/v3/orgs/{org_id}/members",
  ]

  # Analyze routes: no API GW authorizer — Lambda accepts JWT OR X-Api-Key header.
  v3_open_routes = [
    "POST /api/v3/analyze/dockerfile",
    "POST /api/v3/analyze/image",
    "GET /api/v3/health",
  ]
}

resource "aws_apigatewayv2_route" "v3_jwt" {
  for_each = toset(local.v3_jwt_routes)

  api_id             = var.phase1_api_id
  route_key          = each.value
  authorization_type = "JWT"
  authorizer_id      = var.phase2_jwt_authorizer_id
  target             = "integrations/${aws_apigatewayv2_integration.v3.id}"
}

resource "aws_apigatewayv2_route" "v3_open" {
  for_each = toset(local.v3_open_routes)

  api_id    = var.phase1_api_id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.v3.id}"
}

resource "aws_lambda_permission" "api_gw_v3" {
  statement_id  = "AllowAPIGatewayV3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.v3.function_name
  qualifier     = aws_lambda_alias.v3.name
  principal     = "apigateway.amazonaws.com"
  # Wildcard covers all v3 routes including /api/v3/* and /api/v3/health
  source_arn = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${var.phase1_api_id}/*/*"
}
