variable "project_name" { type = string }
variable "environment" { type = string }
variable "frontend_origin" {
  type        = string
  description = "Frontend origin allowed to fetch presigned S3 URLs (CORS)"
}
