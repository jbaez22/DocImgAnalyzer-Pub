# API endpoint: img.craftingnewtech.com → API Gateway custom domain
resource "aws_route53_record" "api" {
  zone_id = var.hosted_zone_id
  name    = var.api_domain_name
  type    = "A"

  alias {
    name                   = var.api_target_domain
    zone_id                = var.api_hosted_zone_id
    evaluate_target_health = false
  }
}

# Frontend: imgapp.craftingnewtech.com → CloudFront distribution
resource "aws_route53_record" "frontend" {
  zone_id = var.hosted_zone_id
  name    = var.frontend_domain_name
  type    = "A"

  alias {
    name                   = var.cloudfront_domain_name
    zone_id                = var.cloudfront_hosted_zone_id
    evaluate_target_health = false
  }
}
