project_name     = "img-analyzer"
environment      = "prod"
aws_region       = "us-east-1"
owner            = "jose"
github_org       = "jbaez22"
github_repo      = "DocImgAnalizer"
alert_email      = "you@example.com"
state_bucket     = "ABC-EXAMPLE-XXXX"
state_lock_table = "ABC-EXAMPLE-XXXX-lock"

phase1_state_key = "docker-img-analyzer/prod/terraform.tfstate"

log_retention_days = 14
free_tier_ttl_days = 30

# VPC
vpc_cidr            = "10.0.0.0/16"
public_subnet_cidr  = "10.0.10.0/24"
private_subnet_cidr = "10.0.20.0/24"
availability_zone   = "us-east-1a"

# Prod has not yet done the NAT Gateway/private-subnet migration dev did on
# 2026-07-09 -- Fargate tasks still run in the public subnet here. Flip this
# to true (matching the default) once that migration is applied to prod.
fargate_use_private_subnet = false

# Cognito
cognito_domain_prefix = "img-analyzer-prod"

# SQS
sqs_visibility_timeout_seconds = 360
sqs_message_retention_seconds  = 345600
sqs_max_receive_count          = 3

# ECS Fargate
fargate_cpu    = 512
fargate_memory = 1024

# ECR
ecr_image_retention_count = 10
