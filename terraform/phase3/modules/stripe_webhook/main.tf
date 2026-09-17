data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ── Secrets Manager — Stripe credentials ─────────────────────────────────────
# Placeholders only — actual values are set manually via AWS Console or CLI.
# Terraform manages the secret resource but not the secret value.

resource "aws_secretsmanager_secret" "stripe_secret_key" {
  name                    = "${var.stripe_secret_manager_path}/secret-key"
  description             = "Stripe secret key (sk_test_* or sk_live_*) - set manually"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "stripe_webhook_secret" {
  name                    = "${var.stripe_secret_manager_path}/webhook-signing-secret"
  description             = "Stripe webhook signing secret - set manually after registering endpoint in Stripe Dashboard"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 7
}

# ── Lambda: Stripe Webhook Handler ───────────────────────────────────────────
resource "aws_cloudwatch_log_group" "webhook" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-stripe-webhook"
  retention_in_days = var.log_retention_days
}

data "archive_file" "webhook_placeholder" {
  type        = "zip"
  output_path = "${path.module}/webhook_placeholder.zip"

  source {
    content  = "# placeholder — replaced by CI pipeline deploy"
    filename = "stripe_handler.py"
  }
}

resource "aws_lambda_function" "webhook" {
  function_name    = "${var.project_name}-${var.environment}-stripe-webhook"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.12"
  handler          = "stripe_handler.handler"
  filename         = data.archive_file.webhook_placeholder.output_path
  source_code_hash = data.archive_file.webhook_placeholder.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      SUBSCRIPTIONS_TABLE        = var.subscriptions_table_name
      STRIPE_SECRET_ARN          = aws_secretsmanager_secret.stripe_secret_key.arn
      STRIPE_WEBHOOK_SECRET_ARN  = aws_secretsmanager_secret.stripe_webhook_secret.arn
      STRIPE_SECRET_MANAGER_PATH = var.stripe_secret_manager_path
      STRIPE_PRO_PRICE_ID        = var.stripe_pro_price_id
      STRIPE_ENTERPRISE_PRICE_ID = var.stripe_enterprise_price_id
      COGNITO_USER_POOL_ID       = var.cognito_user_pool_id
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  depends_on = [aws_cloudwatch_log_group.webhook]
}

# ── API Gateway route: POST /webhooks/stripe ──────────────────────────────────
# No JWT authorizer on this route — Stripe signature verification is done in Lambda.

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = var.phase1_api_id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = var.phase1_api_id
  route_key = "POST /webhooks/stripe"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

resource "aws_lambda_permission" "api_gw_webhook" {
  statement_id  = "AllowAPIGatewayWebhook"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${var.phase1_api_id}/*/*/webhooks/stripe"
}
