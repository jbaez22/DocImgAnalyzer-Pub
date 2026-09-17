output "lambda_exec_role_arn" {
  description = "Lambda execution role ARN"
  value       = aws_iam_role.lambda_exec.arn
}

output "github_actions_role_arn" {
  description = "GitHub Actions OIDC role ARN — add as AWS_ROLE_ARN repo secret"
  value       = aws_iam_role.github_actions.arn
}
