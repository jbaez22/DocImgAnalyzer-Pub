output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "app_client_id" {
  value = aws_cognito_user_pool_client.spa.id
}

output "domain" {
  value = "${aws_cognito_user_pool_domain.main.domain}.auth.${data.aws_region.current.name}.amazoncognito.com"
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.main.arn
}

data "aws_region" "current" {}
