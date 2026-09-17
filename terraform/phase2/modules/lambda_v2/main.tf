data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "lambda_v2" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-api-v2"
  retention_in_days = var.log_retention_days
}

# Bootstrap placeholder — CI pipeline overwrites with real package after first apply.
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = "def handler(event, context): return {'statusCode': 200, 'body': 'placeholder'}"
    filename = "main.py"
  }
}

resource "aws_lambda_function" "api_v2" {
  function_name    = "${var.project_name}-${var.environment}-api-v2"
  role             = var.lambda_exec_role_arn
  handler          = "v2.main.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256
  timeout          = 30
  memory_size      = 512

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      COGNITO_USER_POOL_ID  = var.cognito_user_pool_id
      COGNITO_CLIENT_ID     = var.cognito_client_id
      SQS_QUEUE_URL         = var.sqs_queue_url
      DYNAMODB_TABLE        = var.dynamodb_v2_table_name
      REPORTS_BUCKET        = var.reports_bucket_id
      SBOM_BUCKET           = var.sbom_bucket_id
      ECS_CLUSTER_NAME      = var.ecs_cluster_name
      ECS_TASK_DEFINITION   = var.ecs_task_definition_family
      ECS_SUBNET_IDS        = join(",", var.ecs_subnet_ids)
      ECS_ASSIGN_PUBLIC_IP  = var.ecs_assign_public_ip
      ECS_SECURITY_GROUP_ID = var.ecs_security_group_id
    }
  }

  # AWS-managed encryption (free) -- CMK removed 2026-07-16 per
  # Phase3DeploymentPlanPoC.md item 9

  depends_on = [aws_cloudwatch_log_group.lambda_v2]

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_alias" "v2" {
  name             = "v2"
  function_name    = aws_lambda_function.api_v2.function_name
  function_version = "$LATEST"
}

# ── Cognito JWT Authorizer on Phase 1 API Gateway ────────────────────────────
# Adds JWT authorizer to the existing API Gateway — Phase 1 routes are NOT changed.
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = var.phase1_api_id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.project_name}-${var.environment}-cognito-jwt"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = "https://cognito-idp.${data.aws_region.current.name}.amazonaws.com/${var.cognito_user_pool_id}"
  }
}

# ── Lambda Integration for /api/v2/* ──────────────────────────────────────────
resource "aws_apigatewayv2_integration" "lambda_v2" {
  api_id                 = var.phase1_api_id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.v2.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "v2_proxy" {
  api_id             = var.phase1_api_id
  route_key          = "ANY /api/v2/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda_v2.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "v2_options" {
  api_id    = var.phase1_api_id
  route_key = "OPTIONS /api/v2/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_v2.id}"
}

resource "aws_apigatewayv2_route" "v2_health" {
  api_id    = var.phase1_api_id
  route_key = "GET /api/v2/health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_v2.id}"
}

resource "aws_lambda_permission" "apigw_v2" {
  statement_id  = "AllowAPIGatewayV2Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_v2.function_name
  qualifier     = aws_lambda_alias.v2.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${var.phase1_api_id}/*/*"
}
