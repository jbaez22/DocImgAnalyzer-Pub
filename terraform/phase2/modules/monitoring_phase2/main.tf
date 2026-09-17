data "aws_region" "current" {}

# ── CloudWatch Alarms ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "sqs_dlq_messages" {
  alarm_name          = "${var.project_name}-${var.environment}-phase2-sqs-dlq"
  alarm_description   = "Messages in scan DLQ — indicates failed scan tasks"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_actions       = [var.phase1_sns_topic_arn]
  ok_actions          = [var.phase1_sns_topic_arn]

  dimensions = { QueueName = var.sqs_dlq_name }
}

resource "aws_cloudwatch_metric_alarm" "lambda_v2_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-phase2-lambda-v2-errors"
  alarm_description   = "Lambda v2 error rate elevated"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_actions       = [var.phase1_sns_topic_arn]

  dimensions = { FunctionName = var.lambda_v2_function_name }
}

resource "aws_cloudwatch_metric_alarm" "sqs_queue_depth" {
  alarm_name          = "${var.project_name}-${var.environment}-phase2-sqs-backlog"
  alarm_description   = "SQS scan queue depth > 100 — processing backlog"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 100
  alarm_actions       = [var.phase1_sns_topic_arn]

  dimensions = { QueueName = var.sqs_queue_name }
}

# ── CloudWatch Dashboard ──────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "phase2" {
  dashboard_name = "${var.project_name}-${var.environment}-phase2"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda v2 — Errors / Invocations"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_v2_function_name],
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_v2_function_name],
          ]
          period = 300
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "SQS — Queue Depth / DLQ"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.sqs_queue_name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.sqs_dlq_name],
          ]
          period = 60
          stat   = "Average"
        }
      },
    ]
  })
}
