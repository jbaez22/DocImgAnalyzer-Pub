output "grafana_cloudwatch_role_arn" {
  description = "Paste this into the Grafana Cloud Connect AWS account flow's ARN field"
  value       = aws_iam_role.grafana_cloudwatch.arn
}
