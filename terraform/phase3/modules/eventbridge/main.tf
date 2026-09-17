data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ── Re-scan Trigger Lambda ────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "rescan_trigger" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-rescan-trigger"
  retention_in_days = var.log_retention_days
}

data "archive_file" "rescan_placeholder" {
  type        = "zip"
  output_path = "${path.module}/rescan_placeholder.zip"

  source {
    content  = "# placeholder — replaced by CI pipeline deploy"
    filename = "rescan_trigger.py"
  }
}

resource "aws_lambda_function" "rescan_trigger" {
  function_name    = "${var.project_name}-${var.environment}-rescan-trigger"
  role             = var.lambda_exec_role_arn
  runtime          = "python3.12"
  handler          = "rescan_trigger.handler"
  filename         = data.archive_file.rescan_placeholder.output_path
  source_code_hash = data.archive_file.rescan_placeholder.output_base64sha256
  timeout          = 300
  memory_size      = 256

  environment {
    variables = {
      SUBSCRIPTIONS_TABLE = var.subscriptions_table_name
      SCANS_V2_TABLE      = var.scans_v2_table_name
      ECS_CLUSTER         = var.ecs_cluster
      ECS_TASK_FAMILY     = var.ecs_task_family
      ECS_SUBNET_IDS      = var.ecs_subnet_ids
      ECS_SECURITY_GROUP  = var.ecs_security_group
      MAX_IMAGES_PER_USER = "3"
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  depends_on = [aws_cloudwatch_log_group.rescan_trigger]
}

# ── EventBridge Scheduler — nightly re-scan ───────────────────────────────────
resource "aws_scheduler_schedule" "nightly_rescan" {
  name       = "${var.project_name}-${var.environment}-nightly-rescan"
  group_name = "default"

  flexible_time_window {
    mode                      = "FLEXIBLE"
    maximum_window_in_minutes = 30
  }

  schedule_expression          = var.rescan_schedule_expression
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.rescan_trigger.arn
    role_arn = var.scheduler_role_arn

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}

resource "aws_lambda_permission" "scheduler" {
  statement_id  = "AllowEventBridgeScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rescan_trigger.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.nightly_rescan.arn
}
