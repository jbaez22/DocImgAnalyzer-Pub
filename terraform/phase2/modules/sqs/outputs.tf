output "queue_arn" { value = aws_sqs_queue.scan.arn }
output "queue_url" { value = aws_sqs_queue.scan.url }
output "queue_name" { value = aws_sqs_queue.scan.name }
output "dlq_arn" { value = aws_sqs_queue.dlq.arn }
output "dlq_url" { value = aws_sqs_queue.dlq.url }
output "dlq_name" { value = aws_sqs_queue.dlq.name }
