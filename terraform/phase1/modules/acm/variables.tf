variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "domain_name" {
  description = "Domain name to issue the certificate for"
  type        = string
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID used for DNS validation records"
  type        = string
}
