variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "frontend_bucket_id" {
  description = "S3 frontend bucket name"
  type        = string
}

variable "frontend_bucket_arn" {
  description = "S3 frontend bucket ARN"
  type        = string
}

variable "frontend_bucket_domain_name" {
  description = "S3 frontend bucket regional domain name (used as CloudFront origin)"
  type        = string
}

variable "waf_arn" {
  description = "WAF WebACL ARN (CLOUDFRONT scope)"
  type        = string
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the frontend domain (must be in us-east-1)"
  type        = string
}

variable "domain_name" {
  description = "Frontend custom domain (e.g. imgapp.craftingnewtech.com)"
  type        = string
}
