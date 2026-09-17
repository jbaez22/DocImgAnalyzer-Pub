output "reports_bucket_id" { value = aws_s3_bucket.reports.id }
output "reports_bucket_arn" { value = aws_s3_bucket.reports.arn }
output "sbom_bucket_id" { value = aws_s3_bucket.sbom.id }
output "sbom_bucket_arn" { value = aws_s3_bucket.sbom.arn }
