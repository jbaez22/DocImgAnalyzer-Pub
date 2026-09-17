# SQS-managed SSE (free, AWS-owned key) -- CMK removed 2026-07-16 per
# Phase3DeploymentPlanPoC.md item 9. sqs_managed_sse_enabled must be set
# explicitly -- omitting kms_master_key_id alone does not enable any
# encryption at all (confirmed live: queues had neither KMS nor SSE-SQS
# enabled after the CMK was removed, until this was added).
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-${var.environment}-scan-dlq"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "scan" {
  name                       = "${var.project_name}-${var.environment}-scan-jobs"
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}
