output "lambda_v3_exec_role_arn" {
  description = "Lambda v3 execution role ARN"
  value       = aws_iam_role.lambda_v3_exec.arn
}

output "stripe_webhook_exec_role_arn" {
  description = "Stripe webhook Lambda execution role ARN"
  value       = aws_iam_role.stripe_webhook_exec.arn
}

output "rescan_trigger_exec_role_arn" {
  description = "Re-scan trigger Lambda execution role ARN"
  value       = aws_iam_role.rescan_trigger_exec.arn
}

output "eventbridge_scheduler_role_arn" {
  description = "EventBridge Scheduler role ARN"
  value       = aws_iam_role.eventbridge_scheduler.arn
}

output "github_actions_role_arn" {
  description = "GitHub Actions OIDC role ARN for Phase 3 CI/CD"
  value       = aws_iam_role.github_actions.arn
}
