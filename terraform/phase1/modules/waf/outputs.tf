output "cloudfront_waf_arn" {
  description = "WAF WebACL ARN for CloudFront (CLOUDFRONT scope)"
  value       = aws_wafv2_web_acl.cloudfront.arn
}

