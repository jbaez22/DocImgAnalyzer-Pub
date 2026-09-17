output "api_id" {
  description = "HTTP API ID"
  value       = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "Default API endpoint (before custom domain)"
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "domain_name_target" {
  description = "API Gateway regional domain name — used for Route53 alias target"
  value       = aws_apigatewayv2_domain_name.this.domain_name_configuration[0].target_domain_name
}

output "domain_name_zone_id" {
  description = "API Gateway hosted zone ID — used for Route53 alias"
  value       = aws_apigatewayv2_domain_name.this.domain_name_configuration[0].hosted_zone_id
}
