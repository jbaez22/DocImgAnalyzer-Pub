output "rescan_trigger_function_name" {
  description = "Re-scan trigger Lambda function name"
  value       = aws_lambda_function.rescan_trigger.function_name
}

output "rescan_trigger_function_arn" {
  description = "Re-scan trigger Lambda function ARN"
  value       = aws_lambda_function.rescan_trigger.arn
}

output "schedule_name" {
  description = "EventBridge Scheduler schedule name"
  value       = aws_scheduler_schedule.nightly_rescan.name
}
