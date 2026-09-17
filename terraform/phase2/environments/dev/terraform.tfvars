project_name     = "img-analyzer"
environment      = "dev"
aws_region       = "us-east-1"
owner            = "jose"
github_org       = "jbaez22"
github_repo      = "DocImgAnalizer"
alert_email      = "you@example.com"
state_bucket     = "ABC-EXAMPLE-XXXX"
state_lock_table = "ABC-EXAMPLE-XXXX-lock"

phase1_state_key = "docker-img-analyzer/dev/terraform.tfstate"

log_retention_days = 7
free_tier_ttl_days = 30

# VPC
vpc_cidr            = "10.0.0.0/16"
public_subnet_cidr  = "10.0.10.0/24"
private_subnet_cidr = "10.0.20.0/24"
availability_zone   = "us-east-1a"

# Dev had the NAT Gateway/private-subnet migration applied 2026-07-09 --
# matches the variable default, set explicitly here for discoverability.
fargate_use_private_subnet = true

# Cognito
cognito_domain_prefix = "img-analyzer-dev"

# SQS
sqs_visibility_timeout_seconds = 360
sqs_message_retention_seconds  = 86400
sqs_max_receive_count          = 3

# ECS Fargate
fargate_cpu    = 256
fargate_memory = 512

# ECR
ecr_image_retention_count = 20
