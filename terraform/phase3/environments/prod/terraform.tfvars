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
phase2_state_key = "docker-img-analyzer/phase2/prod/terraform.tfstate"

log_retention_days = 14
free_tier_ttl_days = 30

# Stripe — live mode (sk_live_* keys stored manually in Secrets Manager)
stripe_pro_price_id        = "price_ABC-EXAMPLE-XXXX"
stripe_enterprise_price_id = "price_ABC-EXAMPLE-XXXX"
stripe_secret_manager_path = "img-analyzer/prod/stripe"

# EventBridge
rescan_schedule_expression = "cron(0 2 * * ? *)"
