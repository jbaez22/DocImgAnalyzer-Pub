variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "rate_limit" {
  description = "Max requests per 5-minute window per IP before WAF blocks"
  type        = number
  default     = 1000
}
