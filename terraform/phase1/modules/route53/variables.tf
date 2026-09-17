variable "hosted_zone_id" {
  description = "Route53 hosted zone ID for the parent domain"
  type        = string
}

variable "api_domain_name" {
  description = "API custom domain name"
  type        = string
}

variable "api_target_domain" {
  description = "API Gateway regional domain name (alias target)"
  type        = string
}

variable "api_hosted_zone_id" {
  description = "API Gateway hosted zone ID (alias zone)"
  type        = string
}

variable "frontend_domain_name" {
  description = "Frontend custom domain name"
  type        = string
}

variable "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (alias target)"
  type        = string
}

variable "cloudfront_hosted_zone_id" {
  description = "CloudFront hosted zone ID (constant — alias zone)"
  type        = string
}
