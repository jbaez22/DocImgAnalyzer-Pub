# Initial Manual Steps — Phase 2

These steps must be completed manually before or immediately after the first
`terraform apply` for Phase 2. They cannot be automated by Terraform.

---

## 1. Create GitHub Environments for Phase 2

**Path:** GitHub repo → Settings → Environments

Create two environments:

| Environment name | Protection rules |
|-----------------|-----------------|
| `phase2-development` | None — deploys automatically on push to `phase2` |
| `phase2-production` | Manual approval required (add yourself as required reviewer) |

---

## 2. Add `AWS_ROLE_ARN` Variables

After the first `terraform apply` for Phase 2 dev, get the GitHub Actions role ARN:

```bash
cd terraform/phase2
terraform init -backend-config=environments/dev/backend.hcl
terraform output github_actions_role_arn
```

Then add it in two places:

**Repo-level variable** (fallback, used by phase2-pr.yml for plan):
- Settings → Secrets and variables → Actions → Variables tab
- Add variable: `AWS_ROLE_ARN` = `arn:aws:iam::ABC-EXAMPLE-XXXX:role/img-analyzer-dev-phase2-github-actions`

**Environment-level variable** (overrides repo-level for deploys):
- Settings → Environments → `phase2-development` → Add environment variable
- Name: `AWS_ROLE_ARN`, Value: dev role ARN (same as above)

For production, repeat with the prod role ARN after prod `terraform apply`:
- Settings → Environments → `phase2-production` → Add environment variable
- Name: `AWS_ROLE_ARN_PROD`, Value: `arn:aws:iam::ABC-EXAMPLE-XXXX:role/img-analyzer-prod-phase2-github-actions`

---

## 3. Apply Phase 1 OIDC Trust Patch

The Phase 1 IAM module was updated to add `refs/heads/phase2` to the OIDC trust conditions.
This change must be applied to AWS before Phase 2 CI/CD can authenticate:

```bash
cd terraform/phase1

# Dev
terraform init -backend-config=environments/dev/backend.hcl
terraform apply -var-file=environments/dev/terraform.tfvars -target=module.iam

# Prod
terraform init -backend-config=environments/prod/backend.hcl
terraform apply -var-file=environments/prod/terraform.tfvars -target=module.iam
```

This is the only Phase 1 Terraform change for Phase 2. After applying, Phase 1 resources
are untouched and the Phase 1 Lambda remains live throughout.

---

## 4. First Phase 2 Terraform Apply (dev)

```bash
cd terraform/phase2
terraform init -backend-config=environments/dev/backend.hcl
terraform plan -var-file=environments/dev/terraform.tfvars
# review plan — all resources should be new (no Phase 1 resources modified)
terraform apply -var-file=environments/dev/terraform.tfvars
```

Save the outputs — you will need them for the frontend config:

```bash
terraform output cognito_user_pool_id
terraform output cognito_app_client_id
terraform output ecr_repository_url
terraform output lambda_v2_function_name
```

---

## 5. Initial ECR Push (Scanner Image)

Before ECS can run the scanner, the ECR repository must have at least one image.
Run this once after `terraform apply`:

```bash
ECR_URL=$(cd terraform/phase2 && terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URL

docker build --platform linux/amd64 -t $ECR_URL:latest backend/scanner/
docker push $ECR_URL:latest
```

---

## 6. Verify ECR Scan Results

After the initial push, ECR scans the image automatically (`scan_on_push = true`).
Check for HIGH/CRITICAL findings:

```bash
REPO=$(cd terraform/phase2 && terraform output -raw ecr_repository_url | cut -d/ -f2)
aws ecr describe-image-scan-findings \
  --repository-name $REPO \
  --image-id imageTag=latest \
  --query 'imageScanFindings.findingSeverityCounts'
```

Resolve any CRITICAL or HIGH unfixed findings before running Phase 2 in production.

---

## 7. Frontend Amplify Config

After Phase 2 is deployed to dev, add the Cognito config to the frontend build:

```bash
# In frontend/.env.development.local (git-ignored)
VITE_COGNITO_USER_POOL_ID=<output from terraform>
VITE_COGNITO_APP_CLIENT_ID=<output from terraform>
VITE_API_BASE_URL=https://dev-img.craftingnewtech.com
```

For production, set these as GitHub Actions environment variables in `phase2-production`
so the CI build picks them up without committing them to the repo.

---

## 8. SNS Email Confirmation

The Phase 2 CloudWatch alarms route to the Phase 1 SNS topic, which already has a
confirmed subscription for `you@example.com`. No new subscription is needed.

If deploying to a new account or with a new SNS topic, confirm the subscription by
clicking the link in the confirmation email sent by AWS SNS.

---

## 9. Phase 2 Production Deploy Checklist

Before running `phase2-deploy.yml` against production:

- [ ] Phase 2 dev fully validated (all Definition of Done items checked)
- [ ] Scanner image has no HIGH/CRITICAL unfixed CVEs
- [ ] Lambda v2 `pip-audit` clean
- [ ] Phase 1 Lambda still healthy (check CloudWatch dashboard)
- [ ] GitHub Environment `phase2-production` has required reviewer set
- [ ] Production `AWS_ROLE_ARN_PROD` variable set in environment

---

*DocImgAnalizer Phase 2 — craftingnewtech.com*
