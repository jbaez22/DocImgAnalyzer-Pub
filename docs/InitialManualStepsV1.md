# Initial Manual Steps — Phase 1 Bootstrap

These steps are required **once only**. After completing them, all future deployments
run automatically through GitHub Actions.

---

## Why Manual Steps Are Required

GitHub Actions authenticates to AWS via an IAM OIDC role that does not exist until
Terraform creates it. The very first `terraform apply` per environment must therefore
be run locally. After that, CI owns all infrastructure changes.

---

## Prerequisites

Confirm the following before running any commands:

```bash
# 1. Terraform 1.9+
terraform version

# 2. AWS CLI authenticated with sufficient permissions (admin or power-user)
aws sts get-caller-identity

# 3. Confirm shared state bucket exists (created by PersonalPorfolio2026)
aws s3 ls s3://ABC-EXAMPLE-XXXX
```

---

## Phase A — Bootstrap Dev Environment

```bash
cd /Users/jose/KubeLabs/DocImgAnalizer/terraform

# Initialize with dev backend
terraform init -backend-config=environments/dev/backend.hcl

# Preview — review carefully before applying
terraform plan -var-file=environments/dev/terraform.tfvars

# Apply
# ACM certificate validation is automated via Route53 but can take 5–10 minutes.
# Terraform waits for it automatically — do not interrupt.
terraform apply -var-file=environments/dev/terraform.tfvars

# Save the dev GitHub Actions role ARN — needed in Phase C
terraform output github_actions_role_arn
```

---

## Phase B — Bootstrap Prod Environment

```bash
# Switch backend to prod (-reconfigure avoids migration prompts)
terraform init -backend-config=environments/prod/backend.hcl -reconfigure

# Preview
terraform plan -var-file=environments/prod/terraform.tfvars

# Apply
terraform apply -var-file=environments/prod/terraform.tfvars

# Save the prod GitHub Actions role ARN — needed in Phase C
terraform output github_actions_role_arn
```

---

## Phase C — GitHub Repository Setup

You will need the two role ARNs captured at the end of Phase A and Phase B.

### 1. Create GitHub Environments

Go to: `github.com/jbaez22/DocImgAnalizer` → **Settings** → **Environments** → **New environment**

| Environment | Protection rules |
|-------------|-----------------|
| `development` | None — deploys automatically on push to `develop` |
| `production` | See note below |

**Required reviewers on production (manual approval gate):**

The UI path is:
Settings → Environments → production → **"No repository branch protection rules"**
→ Add branch ruleset → Require a pull request before merging → Require review from specific teams

> **Important:** GitHub shows a warning — *"Your ruleset won't be enforced on this private repository
> until you move to a GitHub Team organization account."*
> Required reviewers for private repos require a **paid GitHub Team plan**.
> On a free personal account this setting exists in the UI but is NOT enforced.
>
> **Current workaround:** The natural gate for production is the branch rule —
> only merges to `main` trigger the prod deployment. No code reaches prod without
> going through a PR. Upgrade to GitHub Team when a formal approval gate is needed.

### 2. Set `AWS_ROLE_ARN` in Each Environment

Add a **variable** (not a secret — role ARNs are not sensitive) inside each environment:

```
Settings → Environments → development → Environment variables
  Name:  AWS_ROLE_ARN
  Value: <dev role ARN from Phase A>

Settings → Environments → production → Environment variables
  Name:  AWS_ROLE_ARN
  Value: <prod role ARN from Phase B>
```

> Environment-level variables override repo-level ones automatically.
> The deploy jobs pick up the correct role per environment with no extra configuration.

### 3. Set the Repo-level `AWS_ROLE_ARN` Variable

This variable is used by the PR validation workflow to run `terraform plan`.

```
Settings → Variables → Actions → New repository variable
  Name:  AWS_ROLE_ARN
  Value: <dev role ARN>
```

> PR plans run against dev by default. PRs targeting `main` plan against prod
> using the environment-level variable set in step 2.

### 4. Confirm SNS Alert Subscription

After `terraform apply` completes, AWS sends a subscription confirmation email to
`you@example.com`. Open that email and click **Confirm subscription** to
activate CloudWatch alerts.

---

## Phase D — Push Code and Hand Off to CI

```bash
cd /Users/jose/KubeLabs/DocImgAnalizer

git init
git remote add origin git@github.com:jbaez22/DocImgAnalizer.git
git checkout -b develop

git add .
git commit -m "feat: Phase 1 MVP — initial implementation"

# Push to develop → triggers deploy.yml → deploys to dev automatically
git push -u origin develop
```

Once dev is validated, open a PR from `develop` → `main`. The `pr.yml` workflow
runs all checks and posts a terraform plan as a PR comment. Merging triggers the
prod deployment, which pauses for manual approval from the required reviewers
configured in the `production` GitHub Environment.

---

## What Terraform Creates (~40 Resources Per Environment)

| Resource | Notes |
|----------|-------|
| KMS CMK | Auto-rotation enabled, 30-day deletion window |
| WAF WebACLs (×2) | CloudFront scope + Regional scope |
| S3 buckets (×3) | Frontend, scan reports, Lambda artifacts |
| DynamoDB table | PAY_PER_REQUEST, 90-day TTL, PITR enabled |
| ACM certificates (×2) | API domain + frontend domain, auto-validated via Route53 |
| Lambda function | Placeholder zip on first apply; CI deploys real code |
| API Gateway HTTP API v2 | Custom domain, WAF attached, CloudWatch access logs |
| CloudFront distribution | OAC, HTTPS-only TLS 1.2, SPA 404 → index.html |
| Route53 A records (×2) | API alias + frontend alias |
| IAM roles (×2) | Lambda execution role + GitHub Actions OIDC CI role |
| CloudWatch alarms (×5) | Lambda errors, p99 latency, throttles, API 5xx, DynamoDB errors |
| CloudWatch dashboard | Unified ops view |
| SNS topic + subscription | Alerts to `you@example.com` |

---

## All Future Deployments

After Phase D, no manual steps are required for any environment.

| Trigger | Result |
|---------|--------|
| Push to `develop` | Auto-deploy to dev |
| PR to `develop` or `main` | Lint, test, security scan, terraform plan posted as PR comment |
| Merge to `main` | Prod deployment — pauses for manual approval |
| `workflow_dispatch` | On-demand deploy to any environment |

Run `make smoke-test` locally at any time to validate the live prod API:

```bash
make smoke-test

# Dev:
make smoke-test API_BASE_URL=https://dev-img.craftingnewtech.com
```
