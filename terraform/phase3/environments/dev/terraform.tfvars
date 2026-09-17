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
phase2_state_key = "docker-img-analyzer/phase2/dev/terraform.tfstate"

log_retention_days = 7
free_tier_ttl_days = 30

# Stripe — test mode (sk_test_* keys stored manually in Secrets Manager)
stripe_pro_price_id        = "price_ABC-EXAMPLE-XXXX"
stripe_enterprise_price_id = "price_ABC-EXAMPLE-XXXX"
stripe_secret_manager_path = "img-analyzer/dev/stripe"

# EventBridge
rescan_schedule_expression = "cron(0 2 * * ? *)"
