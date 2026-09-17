output "lambda_v2_exec_role_arn" { value = aws_iam_role.lambda_v2_exec.arn }
output "fargate_task_role_arn" { value = aws_iam_role.fargate_task.arn }
output "fargate_execution_role_arn" { value = aws_iam_role.fargate_execution.arn }
output "github_actions_role_arn" { value = aws_iam_role.github_actions.arn }
output "github_actions_plan_role_arn" { value = aws_iam_role.github_actions_plan.arn }
