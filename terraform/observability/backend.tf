# Partial backend configuration - no values are hardcoded here.
# Supply the matching .hcl file at init time:
#
#   terraform init -backend-config=environments/prod/backend.hcl

terraform {
  backend "s3" {}
}
