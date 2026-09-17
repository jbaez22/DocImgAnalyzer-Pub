output "frontend_bucket_id" {
  value = aws_s3_bucket.frontend.id
}

output "frontend_bucket_arn" {
  value = aws_s3_bucket.frontend.arn
}

output "frontend_bucket_domain_name" {
  description = "Regional domain name used as the CloudFront origin"
  value       = aws_s3_bucket.frontend.bucket_regional_domain_name
}

output "reports_bucket_id" {
  value = aws_s3_bucket.reports.id
}

output "reports_bucket_arn" {
  value = aws_s3_bucket.reports.arn
}

output "artifact_bucket_id" {
  value = aws_s3_bucket.artifacts.id
}

output "artifact_bucket_arn" {
  value = aws_s3_bucket.artifacts.arn
}
