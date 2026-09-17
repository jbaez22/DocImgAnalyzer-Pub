output "distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "distribution_arn" {
  value = aws_cloudfront_distribution.frontend.arn
}

output "distribution_domain_name" {
  description = "CloudFront distribution domain name (used for Route53 alias)"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "hosted_zone_id" {
  description = "CloudFront hosted zone ID (constant — used for Route53 alias)"
  value       = aws_cloudfront_distribution.frontend.hosted_zone_id
}
