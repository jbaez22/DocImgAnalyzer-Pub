data "aws_region" "current" {}

# ── CloudWatch Alarms ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "stripe_webhook_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-phase3-stripe-webhook-errors"
  alarm_description   = "Stripe webhook Lambda errors - possible signature failure or handler bug"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_actions       = [var.phase1_sns_topic_arn]

  dimensions = { FunctionName = var.stripe_webhook_function_name }
}

resource "aws_cloudwatch_metric_alarm" "lambda_v3_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-phase3-lambda-v3-errors"
  alarm_description   = "Lambda v3 error rate elevated"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_actions       = [var.phase1_sns_topic_arn]

  dimensions = { FunctionName = var.lambda_v3_function_name }
}

resource "aws_cloudwatch_metric_alarm" "rescan_trigger_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-phase3-rescan-errors"
  alarm_description   = "Re-scan trigger Lambda errors - nightly re-scan may have partially failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 86400
  statistic           = "Sum"
  threshold           = 0
  alarm_actions       = [var.phase1_sns_topic_arn]

  dimensions = { FunctionName = var.rescan_trigger_function_name }
}

resource "aws_cloudwatch_metric_alarm" "lambda_v3_throttles" {
  alarm_name          = "${var.project_name}-${var.environment}-phase3-lambda-v3-throttles"
  alarm_description   = "Lambda v3 throttled - may indicate concurrency limits hit"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_actions       = [var.phase1_sns_topic_arn]

  dimensions = { FunctionName = var.lambda_v3_function_name }
}

# ── CloudWatch Dashboard ──────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "phase3" {
  dashboard_name = "${var.project_name}-${var.environment}-phase3"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 8
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "Lambda v3 - Invocations & Errors"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_v3_function_name, { stat = "Sum", period = 300 }],
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_v3_function_name, { stat = "Sum", period = 300, color = "#d13212" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 0
        width  = 8
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "Stripe Webhook - Invocations & Errors"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.stripe_webhook_function_name, { stat = "Sum", period = 300 }],
            ["AWS/Lambda", "Errors", "FunctionName", var.stripe_webhook_function_name, { stat = "Sum", period = 300, color = "#d13212" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 0
        width  = 8
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "Lambda v3 - Duration P50/P99"
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_v3_function_name, { stat = "p50", period = 300, label = "p50" }],
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_v3_function_name, { stat = "p99", period = 300, label = "p99", color = "#ff7f0e" }],
          ]
          view  = "timeSeries"
          yAxis = { left = { label = "ms" } }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "Re-scan Trigger - Invocations"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.rescan_trigger_function_name, { stat = "Sum", period = 86400, label = "Daily runs" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.rescan_trigger_function_name, { stat = "Sum", period = 86400, label = "Errors", color = "#d13212" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          region = data.aws_region.current.name
          title  = "DynamoDB Subscriptions - Read/Write"
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", var.subscriptions_table_name, { stat = "Sum", period = 300 }],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", var.subscriptions_table_name, { stat = "Sum", period = 300, color = "#ff7f0e" }],
          ]
          view    = "timeSeries"
          stacked = false
        }
      },
    ]
  })
}
