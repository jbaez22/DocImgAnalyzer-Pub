variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "lambda_invoke_arn" {
  description = "Lambda live alias invocation ARN"
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name (used for the permission resource)"
  type        = string
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the API custom domain"
  type        = string
}

variable "domain_name" {
  description = "API custom domain name"
  type        = string
}

variable "allowed_origin" {
  description = "CORS allowed origin for the API"
  type        = string
}
