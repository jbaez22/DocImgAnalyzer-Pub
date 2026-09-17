data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Minimal placeholder package — deployed on first terraform apply.
# CI pipeline overwrites this with the real FastAPI package via:
#   aws lambda update-function-code --function-name <name> --s3-bucket <bucket> --s3-key <key>
# lifecycle.ignore_changes ensures Terraform never rolls back the CI-deployed code.
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = <<-EOF
      def handler(event, context):
          return {
              "statusCode": 200,
              "headers": {"Content-Type": "application/json"},
              "body": "{\"status\": \"placeholder — real package deployed by CI\"}"
          }
    EOF
    filename = "main.py"
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-${var.environment}-api"
  description   = "Docker Image Analyzer API — FastAPI via Mangum"
  role          = var.lambda_exec_role_arn
  handler       = "app.main.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 512

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      DYNAMODB_TABLE_NAME = var.dynamodb_table_name
      REPORTS_BUCKET_NAME = var.reports_bucket_id
      ALLOWED_ORIGIN      = var.allowed_origin
      DYNAMODB_TTL_DAYS   = tostring(var.dynamodb_ttl_days)
      LOG_LEVEL           = var.environment == "prod" ? "INFO" : "DEBUG"
    }
  }

  kms_key_arn = var.kms_key_arn

  depends_on = [aws_cloudwatch_log_group.lambda]

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
    ]
  }
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Stable alias — always points to the latest CI-deployed version"
  function_name    = aws_lambda_function.api.function_name
  function_version = "$LATEST"
}
