variable "project_name" { type = string }
variable "environment" { type = string }
variable "cognito_domain_prefix" {
  description = "Prefix for Cognito-hosted UI domain"
  type        = string
}

variable "frontend_url" {
  description = "Frontend URL used as Cognito OAuth callback and logout URL"
  type        = string
}
