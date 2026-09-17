output "key_arn" {
  description = "Phase 3 KMS CMK ARN"
  value       = aws_kms_key.phase3.arn
}

output "key_id" {
  description = "Phase 3 KMS CMK ID"
  value       = aws_kms_key.phase3.key_id
}
