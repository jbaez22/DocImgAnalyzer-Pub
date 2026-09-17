variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet (PoC: single AZ)"
  type        = string
}

variable "availability_zone" {
  description = "Availability zone for the public subnet"
  type        = string
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet — Fargate tasks run here, routed via NAT Gateway"
  type        = string
}

variable "create_private_subnet" {
  description = <<-EOT
    Whether to create the private subnet, NAT Gateway, EIP, and private route
    table at all. False for environments that haven't done the NAT Gateway
    migration -- a simple conditional *reference* elsewhere (e.g. a ternary
    picking public vs private subnet IDs) is not enough to avoid these being
    created, since Terraform's dependency graph includes both branches of a
    ternary regardless of which is selected. Only count = 0 actually removes
    them from the desired state.
  EOT
  type        = bool
  default     = true
}
