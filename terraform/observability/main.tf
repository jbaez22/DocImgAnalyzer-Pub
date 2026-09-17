# Grafana Cloud CloudWatch integration - read-only cross-account role.
# Grafana Cloud assumes this role via STS to read CloudWatch metrics/logs for
# the Grafana dashboards described in docs/grafana/DocImgAnalizer-GrafanaDeploymentPlan-V1.md.
# No long-lived AWS credentials are shared with Grafana Cloud.

data "aws_iam_policy_document" "grafana_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.grafana_aws_account_id}:root"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.grafana_external_id]
    }
  }
}

resource "aws_iam_role" "grafana_cloudwatch" {
  name               = "${var.project_name}-grafana-cloudwatch-readonly"
  description        = "Read-only role assumed by Grafana Cloud to query CloudWatch metrics and logs"
  assume_role_policy = data.aws_iam_policy_document.grafana_assume_role.json
}

data "aws_iam_policy_document" "grafana_cloudwatch_readonly" {
  statement {
    sid    = "CloudWatchMetricsReadOnly"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
      "cloudwatch:GetInsightRuleReport",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CloudWatchLogsReadOnly"
    effect = "Allow"
    actions = [
      "logs:GetLogEvents",
      "logs:GetLogGroupFields",
      "logs:GetLogRecord",
      "logs:StartQuery",
      "logs:StopQuery",
      "logs:GetQueryResults",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ResourceMetadataReadOnly"
    effect = "Allow"
    actions = [
      "tag:GetResources",
      "ec2:DescribeRegions",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "grafana_cloudwatch_readonly" {
  name   = "${var.project_name}-grafana-cloudwatch-readonly"
  role   = aws_iam_role.grafana_cloudwatch.id
  policy = data.aws_iam_policy_document.grafana_cloudwatch_readonly.json
}
