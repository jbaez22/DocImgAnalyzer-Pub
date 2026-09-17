# Docker Image Analyzer — Phase 3 Deployment Plan (Option 2 / PoC)

**Date:** 2026-07-07  
**Target cost:** ~$12/month (all phases combined)  
**Architecture:** PoC — single AZ, public subnet Fargate, AWS-managed encryption, no WAF  
**Stripe mode:** Sandbox (Test mode) — no real payments  
**Reference costs:** `docs/InfrastructureCostPortfolio.md`  
**Scalability:** Documented upgrade path from PoC → Single-AZ → Multi-AZ production

---

## Item Tracking — Completion Status

Reconciled against git history and live AWS/GitHub state on 2026-07-16 — timestamps are
verified (commit dates, AWS resource creation/change dates, `gh api` events), not
recalled from memory. Several plan steps were superseded by later design decisions or
never executed; see the numbered notes below the table for each.

| -- | ------------------------------------------------ | ------------------------------------------------ | --------------------------------------------- |
| #  | Item                                             | Status                                           | Completed                                     |
| -- | ------------------------------------------------ | ------------------------------------------------ | --------------------------------------------- |
| 1  | 0.1-0.3 Stripe account, API keys, product/prices | Done                                             | 2026-07-07/08 (Stripe dashboard)              |
| 2  | 0.4 Apply Phase 3 Terraform (prerequisite)       | Done                                             | 2026-07-08 08:31 EDT                          |
| 3  | 0.5 Register webhook endpoint in Stripe          | Done                                             | 2026-07-08 ~09:00-09:17 EDT                   |
| 4  | 0.6 Store keys in Secrets Manager                | Done                                             | 2026-07-08 09:00:37 / 09:17:41 EDT            |
| 5  | 1.1 Reduce Phase 2 to single AZ                  | Done                                             | 2026-07-07 16:20 EDT                          |
| 6  | 1.2 Remove VPC Interface Endpoints               | Superseded                                       | 2026-07-09 14:21 EDT (dev only)               |
| 7  | 1.3 Move Fargate to public subnet                | Done (dev) / Pending (prod)                      | 2026-07-07 16:20 EDT (dev)                    |
| 8  | 1.4 Remove WAF                                   | Not done                                         | -                                             |
| 9  | 1.5 Switch to AWS-managed encryption             | Not done                                         | -                                             |
| 10 | 1.6 Apply Phase 2 migration                      | Partially done                                   | 2026-07-07 to 2026-07-09                      |
| 11 | 2.1 Terraform phase3 scaffold                    | Done                                             | 2026-07-07                                    |
| 12 | 2.2 DynamoDB v3 tables                           | Done                                             | 2026-07-08 (dev + prod)                       |
| 13 | 2.3 Secrets Manager (Stripe keys)                | Done                                             | 2026-07-08 09:00-09:17 EDT                    |
| 14 | 2.4 Lambda v3                                    | Done                                             | 2026-07-08 13:29 EDT (dev) / 15:29 EDT (prod) |
| 15 | 2.5 Stripe webhook Lambda                        | Done                                             | 2026-07-08                                    |
| 16 | 2.6 EventBridge daily re-scan                    | Done                                             | 2026-07-08                                    |
| 17 | 2.7 API Gateway usage plans                      | Superseded                                       | -                                             |
| 18 | 2.8 IAM Phase3 roles                             | Done                                             | 2026-07-07 to 2026-07-08                      |
| 19 | 2.9 CI/CD pipelines                              | Done                                             | 2026-07-08                                    |
| 20 | 2.10 Frontend build                              | Done                                             | 2026-07-08                                    |
| 21 | 2.11 Full deployment sequence (Steps 0-15)       | Done                                             | 2026-07-07 to 2026-07-08                      |
| 22 | Functional smoke tests (Part 3)                  | Done                                             | 2026-07-08                                    |
| 23 | Frontend demo checklist (Part 3)                 | Assumed done                                     | 2026-07-08                                    |
| 24 | Phase 3 prod deploy                              | Done                                             | 2026-07-08 (Lambda modified 19:29 UTC)        |
| 25 | IAM wildcard hardening (s3:* -> explicit)        | Done (phase2) / Applied but unvalidated (phase3) | 2026-07-16                                    |
| -- | ------------------------------------------------ | ------------------------------------------------ | --------------------------------------------- |

### Notes

1. External to repo; exact time not in AWS/git history.
2. Secrets Manager resources + DynamoDB tables created.
3. Inferred from secret value ordering in item 4.
4. Verified via `aws secretsmanager describe-secret`.
5. Commit `f6acca0`; confirmed in current dev+prod tfvars.
6. Removed, then replaced by a NAT Gateway (`fc5cbbf`) after ECR pull failures. Dev has it; prod does not (drift found 2026-07-16).
7. Prod still missing the public/private subnet split - same drift as item 6.
8. `terraform/phase1/modules/waf` still referenced and attached to CloudFront in both environments.
9. Phase 2 KMS CMK still used by DynamoDB v2, SQS, and S3 buckets.
10. See items 5-9 - 3 of 5 sub-steps done.
11. Commit `43be94a`.
12. subscriptions/api-keys/orgs tables active.
13. See items 3-4.
14. Both `Active`.
15. Deployed alongside Lambda v3.
16. `cron(0 2 * * ? *)` matches this doc exactly.
17. No `api_keys` module exists - replaced by Lambda-based key validation per the Decision Log in PHASE3_ACTION_PLAN.md.
18. Trust policy still references the now-deleted `phase3` branch - needs cleanup.
19. phase3-pr.yml + phase3-deploy.yml - trigger-branch gap discovered 2026-07-16.
20. Auth/dashboard/billing/nav pages all shipped.
21. Merged phase3 -> develop 2026-07-08 16:36 EDT (PR #2).
22. 19/19 passing, per PHASE3_ACTION_PLAN.md.
23. Manual UI checklist, not independently verifiable; inferred from passing smoke tests + active prod resources.
24. PHASE3_ACTION_PLAN.md's Open Items list still marks this pending - that's stale; confirmed active in AWS.
25. Today's session - phase2 fully proven via real CI in dev+prod; phase3 applied to dev AWS only, never CI-validated since its branch was deleted.

**Key deltas worth knowing before planning next steps:**
- Actual monthly cost is higher than this plan's ~$12 target: WAF (item 8) and Phase 2's
  KMS CMK (item 9) were never removed as planned.
- Dev and prod have diverged on networking: dev got a NAT Gateway added 2026-07-09
  (items 6-7) that prod never received — this is the exact drift flagged during today's
  IAM work, independent of it.
- Two "PoC" architecture decisions were later reversed by real implementation needs:
  VPC Interface Endpoints → NAT Gateway (item 6), and "no CMK" for Phase 3 → Phase 3 got
  its own dedicated KMS key anyway (not in this plan's Part 2, confirmed via
  `terraform/phase3/modules/kms_phase3/`).
- The `phase3` branch referenced in IAM trust policies (item 18) and the CI/CD trigger
  (item 19) no longer exists — see the branch-lifecycle discussion from earlier today.

---

## Current State

Phase 1 and Phase 2 are deployed and running on `develop`.

> As of 2026-07-16 the actual deployed state diverges from this table's "Target (PoC)"
> column on two rows — see items 8-9 in the tracking table above. WAF and Phase 2's KMS
> CMK were never removed, so real monthly cost is higher than the ~$12 total below.

| ----------------------- | ------------------------------ | ---------------- | -------------- |
|                         | Current deployment             | Target (PoC)     | Monthly delta  |
| ----------------------- | ------------------------------ | ---------------- | -------------- |
| Phase 2 AZs             | 2 (`us-east-1a`, `us-east-1b`) | 1 (`us-east-1a`) | -$29           |
| VPC Interface Endpoints | 4 × 2 AZ (~$58)                | None ($0)        | -$58           |
| Fargate networking      | Private subnet                 | Public subnet    | $0             |
| KMS CMKs                | 5 keys (~$5)                   | AWS-managed ($0) | -$5            |
| WAF                     | CloudFront WebACL (~$5)        | None ($0)        | -$5            |
| Phase 3 (new)           | Not yet deployed               | PoC style        | +$3            |
| **Total**               | **~$81/month**                 | **~$12/month**   | **-$69/month** |
| ----------------------- | ------------------------------ | ---------------- | -------------- |

---

## Deployment Plan Overview

This plan has three parts executed in order:

```
Part 1 — Migrate Phase 2 to PoC    (~30 min)   saves ~$69/month
Part 2 — Deploy Phase 3 PoC        (~2 hours)  adds frontend + billing
Part 3 — Validate + document        (~1 hour)   demo-ready
```

---

## Part 0 — Stripe Account Setup (One-Time, Before Any `terraform apply`)

> **Do this before touching Terraform.** Phase 3 `terraform.tfvars` requires Stripe
> Price IDs that only exist after you create the products. The Webhook signing secret
> is only available after you register the endpoint URL, which only exists after
> `terraform apply` — so the sequence is: account → products → keys in tfvars →
> apply → register webhook → store signing secret in Secrets Manager.

---

### 0.1 — Create a Stripe Account

1. Go to **[stripe.com/register](https://stripe.com/register)**
2. Sign up with `you@example.com`
3. Complete email verification
4. On the "Tell us about your business" screen:
   - Business type: **Individual / Sole proprietor**
   - Industry: **Software / SaaS**
   - Website: `https://imgapp.craftingnewtech.com`
5. Skip card activation for now — you are using **Sandbox (Test mode) only** for this portfolio project

> **Confirm Sandbox mode:** The Stripe Dashboard should show a **"Sandbox"** toggle in the
> top-left (next to the Stripe logo). All API keys, products, and webhooks in this guide are
> Sandbox (test mode) only. Do **not** activate Production mode or enter a bank account.

---

### 0.2 — Get Your API Keys

1. In the Stripe Dashboard, go to **Developers → API keys**
2. Note the two keys (these are Sandbox/test-mode keys — safe to use in dev):

   | ------------------- | ------------- | ------------------------------------------------------------------------------------------------- |
   | Key                 | Format        | Where it goes                                                                                     |
   | ------------------- | ------------- | ------------------------------------------------------------------------------------------------- |
   | **Publishable key** | `pk_test_...` | Vite env var `VITE_STRIPE_PUBLISHABLE_KEY` (in `.env.development` and as a GitHub Actions secret) |
   | **Secret key**      | `sk_test_...` | AWS Secrets Manager — stored manually in step 0.5                                                 |
   | ------------------- | ------------- | ------------------------------------------------------------------------------------------------- |

3. Click **"Reveal test key"** to copy the secret key — save it somewhere safe temporarily.

> The publishable key is safe to include in frontend builds (it is public by design).
> The secret key must **never** appear in code, `.env` files committed to git, or
> Terraform state — it goes into Secrets Manager only.

---

### 0.3 — Create the Product and Prices

Stripe represents your plans as **Products** with **Prices** attached.

#### Create the product

1. Go to **Product catalog → + Add product**
2. Fill in:
   - **Name:** `Docker Image Analyzer`
   - **Description:** `Automated Dockerfile and container image security analysis`
   - **Image:** _(optional — skip for now)_
3. Click **Save product**

#### Add the Pro price

1. On the product detail page, click **+ Add price**
2. Settings:
   - **Pricing model:** Standard pricing
   - **Price:** `19.00`
   - **Currency:** USD
   - **Billing period:** Monthly
   - **Nickname:** `Pro` _(helps you identify it in API responses)_
3. Click **Save price**
4. **Copy the Price ID** — it looks like `price_1AbCdEfGhIjKlMnO...`

#### Add the Enterprise price

1. Click **+ Add price** again
2. Settings:
   - **Pricing model:** Standard pricing
   - **Price:** `99.00`
   - **Currency:** USD
   - **Billing period:** Monthly
   - **Nickname:** `Enterprise`
3. Click **Save price**
4. **Copy the Price ID**

#### Update `terraform.tfvars` with the real Price IDs

**File:** `terraform/phase3/environments/dev/terraform.tfvars`

```hcl
# Replace the REPLACE_ME placeholders with the real IDs from step 0.3
stripe_pro_price_id        = "price_1AbCdEfGhIjKlMnO..."   # your actual Pro price ID
stripe_enterprise_price_id = "price_1XyZaBcDeFgHiJkL..."   # your actual Enterprise price ID
```

> `prod/terraform.tfvars` uses the same Sandbox/test-mode IDs for now. When you switch to Production
> mode later, you will create new prices under the same product and update `prod/terraform.tfvars`.

---

### 0.4 — Apply Phase 3 Terraform (Prerequisite for Webhook Registration)

Before you can register a webhook, the `/webhooks/stripe` API Gateway route must exist.
Skip ahead to Part 2 → Section 2.11 Steps 1–8, then return here to complete 0.5 and 0.6.

```
Do Part 0.1 → 0.3 (this section)
Then do Part 1 (migrate Phase 2)
Then do Part 2 (deploy Phase 3 infra)
Then return here for Part 0.5 and 0.6 (webhook + Secrets Manager)
```

---

### 0.5 — Register the Webhook Endpoint in Stripe

> Do this **after** `terraform apply` has created the Phase 3 Lambda and API Gateway route.

1. In the Stripe Dashboard, go to **Developers → Webhooks → + Add endpoint**
2. Fill in:
   - **Endpoint URL:**
     - Dev: `https://dev-img.craftingnewtech.com/webhooks/stripe`
     - Prod: `https://img.craftingnewtech.com/webhooks/stripe`
3. Under **"Listen to"**, select **"Events on your account"**
4. Click **"+ Select events"** and add all five:

   | ------------------------------- | --------------------------------------------- |
   | Event                           | Triggered when                                |
   | ------------------------------- | --------------------------------------------- |
   | `checkout.session.completed`    | User completes Stripe Checkout                |
   | `customer.subscription.updated` | Plan change, renewal, trial end               |
   | `customer.subscription.deleted` | Cancellation or payment failure               |
   | `invoice.payment_failed`        | Payment declined                              |
   | `invoice.payment_succeeded`     | Successful renewal — reset monthly scan count |
   | ------------------------------- | --------------------------------------------- |

5. Click **Add endpoint**
6. On the webhook detail page, click **"Reveal"** under **Signing secret**
7. **Copy the signing secret** — it looks like `whsec_...`

---

### 0.6 — Store Keys in AWS Secrets Manager

The Stripe Webhook Lambda reads both secrets at cold start.
Store them using the AWS CLI (run once — not managed by Terraform to keep secrets out of state):

```bash
# Store the Stripe secret key (sk_test_...)
aws secretsmanager put-secret-value \
  --secret-id "img-analyzer/dev/stripe/secret-key" \
  --secret-string "sk_test_YOUR_SECRET_KEY_HERE" \
  --region us-east-1

# Store the webhook signing secret (whsec_...)
aws secretsmanager put-secret-value \
  --secret-id "img-analyzer/dev/stripe/webhook-signing-secret" \
  --secret-string "whsec_YOUR_SIGNING_SECRET_HERE" \
  --region us-east-1
```

> The `secret-id` paths match `var.stripe_secret_manager_path` in `terraform.tfvars`
> (`img-analyzer/dev/stripe`). Terraform created the secret *resources* during apply —
> you are only setting the *value* here.

**Verify the secrets are readable by Lambda:**

```bash
# Should return the secret value (not an error)
aws secretsmanager get-secret-value \
  --secret-id "img-analyzer/dev/stripe/secret-key" \
  --region us-east-1 \
  --query SecretString \
  --output text
```

---

### 0.7 — Stripe Setup Checklist

- [ ] Stripe account created, email verified
- [ ] Dashboard is showing **Sandbox (Test mode)** (purple banner)
- [ ] Product "Docker Image Analyzer" created with two prices (Pro $19, Enterprise $99)
- [ ] Pro Price ID copied → added to `terraform/phase3/environments/dev/terraform.tfvars`
- [ ] Enterprise Price ID copied → added to `terraform/phase3/environments/dev/terraform.tfvars`
- [ ] Publishable key (`pk_test_...`) noted — will be added to frontend env vars in Step 2.10
- [ ] Secret key (`sk_test_...`) stored in Secrets Manager at `img-analyzer/dev/stripe/secret-key`
- [ ] Webhook endpoint registered at `https://dev-img.craftingnewtech.com/webhooks/stripe`
- [ ] All 5 webhook events selected
- [ ] Signing secret (`whsec_...`) stored in Secrets Manager at `img-analyzer/dev/stripe/webhook-signing-secret`

---

## Part 1 — Migrate Phase 2 to PoC Architecture

> **Why do this first:** Phase 2 is the dominant cost driver. Migrating before building
> Phase 3 means you start Phase 3 with a clean, low-cost baseline.

### 1.1 — Reduce to Single AZ

**File:** `terraform/phase2/environments/dev/terraform.tfvars`

```hcl
# BEFORE
availability_zones   = ["us-east-1a", "us-east-1b"]
private_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]

# AFTER
availability_zones   = ["us-east-1a"]
private_subnet_cidrs = ["10.0.1.0/24"]
```

**Impact:** Removes the second private subnet and all second-AZ endpoint ENIs. Saves ~$29/month.

---

### 1.2 — Remove VPC Interface Endpoints

**File:** `terraform/phase2/modules/vpc/main.tf`

Comment out or delete the four Interface endpoint resources:

```hcl
# REMOVE these four resources (keep the two Gateway endpoints — they are free)
# resource "aws_vpc_endpoint" "ecr_api"  { ... }
# resource "aws_vpc_endpoint" "ecr_dkr"  { ... }
# resource "aws_vpc_endpoint" "sqs"      { ... }
# resource "aws_vpc_endpoint" "logs"     { ... }

# KEEP — Gateway endpoints are free and improve performance
resource "aws_vpc_endpoint" "s3"       { vpc_endpoint_type = "Gateway" ... }
resource "aws_vpc_endpoint" "dynamodb" { vpc_endpoint_type = "Gateway" ... }
```

Also remove the `aws_security_group.vpc_endpoints` resource and any references to it.

**Saves:** ~$58/month

---

### 1.3 — Move Fargate to Public Subnet

Fargate tasks need internet access to reach ECR, SQS, and CloudWatch Logs once VPC
Interface Endpoints are removed. The solution: assign a public IP and use a public subnet.

**Step A — Add a public subnet to the VPC module**

**File:** `terraform/phase2/modules/vpc/main.tf`

```hcl
resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false   # we set this per-task, not per-subnet

  tags = { Name = "${var.project_name}-${var.environment}-public-${var.availability_zones[count.index]}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-${var.environment}-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.project_name}-${var.environment}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
```

Add to `variables.tf`:
```hcl
variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24"]
}
```

Add to `terraform.tfvars`:
```hcl
public_subnet_cidrs = ["10.0.10.0/24"]
```

**Step B — Update Fargate security group**

```hcl
# Fargate task SG — PoC mode
# No inbound. Outbound: HTTPS only (ECR, SQS, CloudWatch, DynamoDB over internet)
resource "aws_security_group" "fargate_task" {
  name   = "${var.project_name}-${var.environment}-fargate-task"
  vpc_id = var.vpc_id

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS to AWS services (ECR, SQS, CloudWatch, DynamoDB)"
  }
}
```

**Step C — Update EventBridge Pipe network config**

**File:** `terraform/phase2/modules/ecs/main.tf`

```hcl
network_configuration {
  aws_vpc_configuration {
    subnets          = var.public_subnet_ids    # was: private_subnet_ids
    security_groups  = [var.fargate_task_sg_id]
    assign_public_ip = "ENABLED"               # was: "DISABLED"
  }
}
```

Update module variables and outputs accordingly to pass `public_subnet_ids`.

---

### 1.4 — Remove WAF

**File:** `terraform/phase1/modules/waf/main.tf` (or wherever WAF is defined)

Comment out the WAF WebACL resource and its association with CloudFront.
Replace the CloudFront distribution's `web_acl_id` argument with `null` or remove it.

API Gateway already has throttling configured — that remains as the rate-limiting layer.

**Saves:** ~$5/month

---

### 1.5 — Switch to AWS-Managed Encryption

Remove Phase 2 KMS CMK and update all resources to use AWS-managed keys.

**DynamoDB v2:** Remove `server_side_encryption { kms_key_arn }` block — DynamoDB uses AWS-owned CMK by default (free).

**S3 phase2 buckets:** Change to `SSE-S3`:
```hcl
server_side_encryption_configuration {
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"   # was: "aws:kms" with kms_key_arn
    }
  }
}
```

**SQS:** Remove `kms_master_key_id` — SQS uses AWS-managed key by default (free).

**Lambda v2 environment:** Remove `kms_key_arn` argument — Lambda uses AWS-managed encryption by default (free).

> **Note:** Phase 1 KMS CMKs are in `terraform/phase1/` — do not touch them. Phase 1 is frozen.
> Phase 1 CMK cost (~$3/month) is accepted as-is.

---

### 1.6 — Apply Phase 2 Migration

```bash
cd terraform/phase2

# Preview changes
terraform plan -var-file=environments/dev/terraform.tfvars

# Review the plan carefully:
# - VPC endpoints destroyed: 4 Interface endpoints
# - Fargate SG updated: egress rule changed
# - Public subnet created
# - EventBridge Pipe network config updated
# - KMS CMK destroyed (after resources move to AWS-managed keys)

# Apply
terraform apply -var-file=environments/dev/terraform.tfvars
```

**Verify Fargate still works after migration:**
```bash
# Submit a test scan via the API and confirm it completes
curl -X POST https://dev-img.craftingnewtech.com/api/v2/analyze/image \
  -H "Authorization: Bearer <cognito_token>" \
  -H "Content-Type: application/json" \
  -d '{"image_name": "nginx:1.25.3"}'
```

Confirm the scan reaches COMPLETE status. If it fails, the Fargate task likely cannot
reach ECR or SQS — check the security group egress rules and `assignPublicIp` setting.

---

## Part 2 — Deploy Phase 3 (PoC Style)

All Phase 3 resources use PoC principles: AWS-managed encryption, single AZ, no WAF additions.

### 2.1 — Terraform Phase 3 Directory Structure

```
terraform/phase3/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
├── backend.tf
├── environments/
│   ├── dev/
│   │   ├── backend.hcl
│   │   └── terraform.tfvars
│   └── prod/
│       ├── backend.hcl
│       └── terraform.tfvars
└── modules/
    ├── dynamodb_v3/        # subscriptions, api-keys, orgs tables
    ├── lambda_v3/          # FastAPI v3 + entitlement middleware
    ├── stripe_webhook/     # Stripe webhook Lambda + API GW route
    ├── api_keys/           # API Gateway usage plans
    ├── eventbridge/        # Daily re-scan scheduler
    ├── iam_phase3/         # GitHub Actions role + Lambda roles
    └── monitoring_phase3/  # Basic CloudWatch logs (no dashboards for PoC)
```

**State backend** (`environments/dev/backend.hcl`):
```hcl
bucket  = "ABC-EXAMPLE-XXXX"
key     = "docker-img-analyzer/phase3/dev/terraform.tfstate"
region  = "us-east-1"
encrypt = true
use_lockfile = true
```

---

### 2.2 — DynamoDB v3 Module (PoC)

Three tables with AWS-managed encryption (no CMK):

```hcl
resource "aws_dynamodb_table" "subscriptions" {
  name         = "${var.project_name}-${var.environment}-subscriptions"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "user_id"

  attribute { name = "user_id" type = "S" }

  point_in_time_recovery { enabled = true }

  # PoC: AWS-owned CMK — free
  server_side_encryption { enabled = true }
}

resource "aws_dynamodb_table" "api_keys" {
  name         = "${var.project_name}-${var.environment}-api-keys"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "key_id"
  range_key = "user_id"

  attribute { name = "key_id"  type = "S" }
  attribute { name = "user_id" type = "S" }

  global_secondary_index {
    name            = "user-keys-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

resource "aws_dynamodb_table" "orgs" {
  name         = "${var.project_name}-${var.environment}-orgs"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "org_id"

  attribute { name = "org_id" type = "S" }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}
```

**Monthly cost:** ~$1–2 (on-demand, minimal traffic)

---

### 2.3 — Secrets Manager (Stripe Test Keys)

Stored manually — not managed by Terraform. Terraform reads them at runtime.

```bash
# Run once manually — store Stripe TEST keys (not live)
aws secretsmanager create-secret \
  --name "img-analyzer/dev/stripe-secret-key" \
  --secret-string "sk_test_YOUR_TEST_KEY_HERE" \
  --region us-east-1

aws secretsmanager create-secret \
  --name "img-analyzer/dev/stripe-webhook-secret" \
  --secret-string "whsec_YOUR_WEBHOOK_SECRET_HERE" \
  --region us-east-1
```

Lambda reads these at cold start via `boto3.client("secretsmanager")`.  
**Monthly cost:** $0.40 × 2 = ~$1/month

---

### 2.4 — Lambda v3 Module (PoC)

FastAPI v3 with entitlement middleware. Same pattern as Lambda v2.
No CMK — uses AWS-managed Lambda encryption for environment variables.

```hcl
resource "aws_lambda_function" "api_v3" {
  function_name = "${var.project_name}-${var.environment}-api-v3"
  role          = var.lambda_exec_role_arn
  handler       = "v3.main.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 512

  # PoC: no kms_key_arn — AWS-managed encryption
  environment {
    variables = {
      ENVIRONMENT              = var.environment
      COGNITO_USER_POOL_ID     = var.cognito_user_pool_id
      COGNITO_CLIENT_ID        = var.cognito_client_id
      DYNAMODB_V2_TABLE        = var.dynamodb_v2_table_name
      DYNAMODB_SUBSCRIPTIONS   = var.subscriptions_table_name
      DYNAMODB_API_KEYS        = var.api_keys_table_name
      DYNAMODB_ORGS            = var.orgs_table_name
      SQS_QUEUE_URL            = var.sqs_queue_url
      STRIPE_SECRET_ARN        = var.stripe_secret_arn
      STRIPE_PUBLISHABLE_KEY   = var.stripe_publishable_key
    }
  }

  lifecycle { ignore_changes = [filename, source_code_hash] }
}
```

Routes added to the **existing Phase 1 API Gateway** (same pattern as Phase 2):

```hcl
resource "aws_apigatewayv2_route" "v3_proxy" {
  api_id             = var.phase1_api_id
  route_key          = "ANY /api/v3/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda_v3.id}"
  authorization_type = "JWT"
  authorizer_id      = var.cognito_authorizer_id   # reuse Phase 2 authorizer
}
```

---

### 2.5 — Stripe Webhook Lambda

Separate Lambda — no JWT authorizer on this route (Stripe signs with HMAC, not JWT).

```hcl
resource "aws_apigatewayv2_route" "stripe_webhook" {
  api_id    = var.phase1_api_id
  route_key = "POST /webhooks/stripe"
  target    = "integrations/${aws_apigatewayv2_integration.stripe_webhook.id}"
  # No authorization_type — Stripe uses HMAC signature, not JWT
}
```

---

### 2.6 — EventBridge Scheduler (Daily Re-scan)

```hcl
resource "aws_scheduler_schedule" "daily_rescan" {
  name = "${var.project_name}-${var.environment}-daily-rescan"

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(0 2 * * ? *)"   # 02:00 UTC daily
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.rescan_trigger.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
```

**Monthly cost:** ~$0 (well within EventBridge free tier)

---

### 2.7 — API Gateway Usage Plans

```hcl
resource "aws_api_gateway_usage_plan" "pro" {
  name = "${var.project_name}-${var.environment}-pro"

  throttle_settings {
    rate_limit  = 10
    burst_limit = 20
  }

  quota_settings {
    limit  = 200
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan" "enterprise" {
  name = "${var.project_name}-${var.environment}-enterprise"

  throttle_settings {
    rate_limit  = 50
    burst_limit = 100
  }

  # No quota — Enterprise is unlimited
}
```

---

### 2.8 — IAM Phase 3 Roles

Same pattern as Phase 2 — OIDC-based GitHub Actions role + Lambda execution role.
Scoped to Phase 3 resources only. Phase 1 and Phase 2 roles are not modified.

```hcl
# GitHub Actions trust — allow phase3 branch + develop + pull_request
condition {
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values = [
    "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/phase3",
    "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/develop",
    "repo:${var.github_org}/${var.github_repo}:pull_request",
    "repo:${var.github_org}/${var.github_repo}:environment:phase3-development",
  ]
}
```

---

### 2.9 — CI/CD Pipelines

Two new workflow files — same pattern as Phase 2 pipelines:

**`.github/workflows/phase3-pr.yml`** — triggers on PR to `develop`
- Path filter: `terraform/phase3/**`, `backend/v3/**`, `frontend/**`
- Jobs: TF validate, TF plan (dev), ruff lint, mypy, pytest, Trivy IaC

**`.github/workflows/phase3-deploy.yml`** — triggers on push to `develop`
- Path filter: same as above
- Jobs: TF apply (dev), Lambda v3 deploy, Stripe webhook Lambda deploy, frontend S3 sync + CloudFront invalidation
- Environment: `phase3-development` (auto) / `phase3-production` (manual approval)

---

### 2.10 — Frontend Build

Install Amplify Auth and build Phase 3 pages (see `PHASE3_ACTION_PLAN.md` Steps 6a–6d):

```bash
cd frontend
npm install @aws-amplify/auth @aws-amplify/core recharts

# Vite env vars (.env.development)
VITE_COGNITO_USER_POOL_ID=us-east-1_ABC-EXAMPLE-XXXX
VITE_COGNITO_CLIENT_ID=ABC-EXAMPLE-XXXX
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_YOUR_TEST_KEY_HERE
VITE_API_BASE_URL=https://dev-img.craftingnewtech.com

npm run build
```

Deploy via CI — the `phase3-deploy.yml` pipeline handles S3 sync and CloudFront invalidation automatically on push to `develop`.

---

### 2.11 — Step-by-Step Deployment Sequence

Run in this order:

```
Step 0  Stripe account setup (Part 0.1 → 0.3) — get price IDs before touching Terraform
Step 1  git checkout -b phase3
Step 2  Scaffold terraform/phase3/ directory + all modules (no apply yet)           ✅ Done
Step 3  Update terraform.tfvars with real Stripe Price IDs (from Part 0.3)
Step 4  Part 1 — migrate Phase 2 to PoC (terraform apply phase2)
Step 5  Write backend/v3/ — FastAPI v3 + routers + entitlement middleware
Step 6  Write backend/webhooks/stripe_handler.py
Step 7  Write unit tests — pytest, >80% coverage
Step 8  Run make check — TF fmt, ruff, mypy, TF validate, Trivy IaC, Docker build
Step 9  terraform init + terraform plan (dev) — review all Phase 3 resources
Step 10 terraform apply (dev) — deploy Phase 3 infrastructure
Step 11 Register Stripe webhook endpoint + store keys in Secrets Manager (Part 0.5 → 0.6)
Step 12 Deploy Lambda v3 + Stripe webhook Lambda via pipeline
Step 13 Build + deploy frontend (auth pages → dashboard → billing pages)
Step 14 Run smoke test checklist (see Part 3)
Step 15 Merge phase3 → develop
```

---

## Part 3 — Validate + Demo-Ready Checklist

### Functional Smoke Tests

```bash
BASE=https://dev-img.craftingnewtech.com
TOKEN="<cognito_jwt>"

# Phase 1 regression (anonymous)
curl $BASE/api/v1/analyze -d '{"dockerfile":"FROM ubuntu:latest"}' -H "Content-Type: application/json"
# Expect: 200 with score and findings

# Phase 2 regression (authenticated)
curl $BASE/api/v2/health -H "Authorization: Bearer $TOKEN"
# Expect: {"status":"ok","version":"2"}

# Phase 3 billing status
curl $BASE/api/v3/billing/status -H "Authorization: Bearer $TOKEN"
# Expect: {"tier":"free","scan_count":0,"scan_limit":10}

# Phase 3 Stripe checkout (test mode)
curl -X POST $BASE/api/v3/billing/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"price_id":"price_test_YOUR_PRO_PRICE_ID"}'
# Expect: {"checkout_url":"https://checkout.stripe.com/..."}

# Stripe test card: 4242 4242 4242 4242, any expiry, any CVC
# Complete checkout → webhook fires → tier updates to "pro"

# Verify tier updated
curl $BASE/api/v3/billing/status -H "Authorization: Bearer $TOKEN"
# Expect: {"tier":"pro","scan_count":0,"scan_limit":200}

# Create API key
curl -X POST $BASE/api/v3/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"test-key"}'
# Expect: {"key_id":"...","raw_key":"dia_..."}   ← copy this, shown once

# Use API key
curl -X POST $BASE/api/v3/analyze/dockerfile \
  -H "X-Api-Key: dia_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"dockerfile":"FROM node:18-alpine\nRUN npm install\n"}'
# Expect: 200 with analysis

# Entitlement gate
# New free-tier account → try deep scan → expect 403
curl -X POST $BASE/api/v3/analyze/image \
  -H "Authorization: Bearer <free_user_token>" \
  -H "Content-Type: application/json" \
  -d '{"image_name":"nginx:1.25.3"}'
# Expect: 403 "Deep scanning requires a Pro or Enterprise plan."
```

### Frontend Demo Checklist

- [ ] Sign up → verify email → land on Dashboard
- [ ] Dashboard loads scan history (empty for new user)
- [ ] Click New Scan → submit `nginx:1.25.3` → status polling works → COMPLETE shown
- [ ] CVE table renders, SBOM download link works
- [ ] Pricing page loads with correct tier comparison table
- [ ] Click Upgrade → Stripe Checkout page opens (test mode)
- [ ] Complete payment with `4242 4242 4242 4242` → return to app → tier badge updates to PRO
- [ ] Billing page shows correct plan + scan usage meter
- [ ] Create API key → raw key shown in modal → copy it
- [ ] Revoke key → confirmed gone from key list
- [ ] Sign out → Sign in again → session restored correctly

---

## Scalability Path — PoC to Production

This architecture is designed to scale up with minimal code changes. Every upgrade is
a **Terraform configuration change** — no application code changes required.

### Tier 0 → Tier 1: Add Second AZ (~$52/month)

```hcl
# terraform/phase2/environments/dev/terraform.tfvars
availability_zones   = ["us-east-1a", "us-east-1b"]
private_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
public_subnet_cidrs  = ["10.0.10.0/24", "10.0.11.0/24"]
```

**Trigger:** First real user onboarded or demo showed to a potential client.  
**Result:** Survives an AZ-level outage, qualifies for 99.9%+ SLA.

---

### Tier 1 → Tier 2: Add VPC Interface Endpoints (~$62/month Phase 2)

Restore private networking — move Fargate back to private subnets:

```hcl
# terraform/phase2/modules/vpc/main.tf — restore these resources
resource "aws_vpc_endpoint" "ecr_api" { vpc_endpoint_type = "Interface" ... }
resource "aws_vpc_endpoint" "ecr_dkr" { vpc_endpoint_type = "Interface" ... }
resource "aws_vpc_endpoint" "sqs"     { vpc_endpoint_type = "Interface" ... }
resource "aws_vpc_endpoint" "logs"    { vpc_endpoint_type = "Interface" ... }
```

```hcl
# EventBridge Pipe — revert to private
assign_public_ip = "DISABLED"
subnets          = var.private_subnet_ids
```

**Trigger:** Enterprise customer inquires, compliance review required, or revenue >$200/month.  
**Result:** Zero internet egress from scanner tasks — fully private networking.

---

### Tier 2 → Tier 3: Add KMS CMKs (~$81/month)

```hcl
# terraform/phase2/modules/kms_phase2/main.tf — restore CMK
resource "aws_kms_key" "phase2" { ... }

# terraform/phase2/modules/dynamodb_v2/main.tf
server_side_encryption { kms_key_arn = var.kms_key_arn }

# terraform/phase2/modules/s3_phase2/main.tf
server_side_encryption_configuration {
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
  }
}
```

**Trigger:** SOC2 audit, HIPAA requirement, or enterprise contract requires customer-managed keys.  
**Result:** You hold the encryption keys — full cryptographic control.

---

### Tier 3 → Tier 4: Add WAF (~$86/month)

```hcl
# terraform/phase1/modules/waf/main.tf — restore WebACL
resource "aws_wafv2_web_acl" "main" {
  scope = "CLOUDFRONT"
  ...
}

# terraform/phase1/modules/cdn/main.tf — re-attach
resource "aws_cloudfront_distribution" "frontend" {
  web_acl_id = var.waf_web_acl_arn
  ...
}
```

**Trigger:** Detecting abuse patterns, rate-limit bypass attempts, or preparing for public launch.  
**Result:** SQL injection protection, geo-blocking, IP reputation filtering.

---

### Tier 4 → Tier 5: Auto-Scaling Fargate (~variable)

Add SQS-depth-based auto-scaling via Application Auto Scaling:

```hcl
resource "aws_appautoscaling_target" "fargate" {
  service_namespace  = "ecs"
  resource_id        = "service/${var.ecs_cluster_name}/${var.ecs_service_name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 10   # max concurrent scanner tasks
}

resource "aws_appautoscaling_policy" "sqs_depth" {
  name               = "sqs-depth-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.fargate.resource_id
  scalable_dimension = aws_appautoscaling_target.fargate.scalable_dimension
  service_namespace  = aws_appautoscaling_target.fargate.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 5   # scale up when SQS depth > 5 messages per task
    customized_metric_specification {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      statistic   = "Average"
    }
  }
}
```

**Trigger:** Sustained scan volume requiring parallel processing (>50 concurrent scans).  
**Result:** Scales from 0 tasks (idle) to 10 tasks automatically based on SQS queue depth.

---

### Scalability Summary

| ---------------------- | --------------------------------- | ---------------- | ---------------------- |
| Tier                   | Config change                     | Monthly cost     | Trigger                |
| ---------------------- | --------------------------------- | ---------------- | ---------------------- |
| **0 — PoC**            | Current target                    | **~$12**         | Portfolio / demo       |
| 1 — Multi-AZ           | Add second AZ in tfvars           | **~$52**         | First real users       |
| 2 — Private networking | Add VPC Interface Endpoints       | **~$81**         | Enterprise inquiry     |
| 3 — CMK encryption     | Add KMS module + update resources | **~$86**         | Compliance requirement |
| 4 — WAF                | Restore WAF WebACL                | **~$91**         | Public launch / abuse  |
| 5 — Auto-scaling       | Add AppAutoScaling + SQS policy   | **~$91 + usage** | High scan volume       |
| ---------------------- | --------------------------------- | ---------------- | ---------------------- |

Every step is reversible. No application code changes at any tier — Terraform config only.

---

## Cost Summary — Option 2 (PoC)

```
Phase 1:  ~$6/month   (CloudFront, API GW, Lambda, DDB, S3, Route53, CloudWatch)
Phase 2:  ~$4/month   (ECR, Cognito, SQS, DDB v2, Lambda v2, S3 buckets)
Phase 3:  ~$3/month   (Secrets Manager, DDB v3, Lambda v3, EventBridge)
──────────────────────────────────────────────────────────────────────────────
Total:    ~$12/month  (zero scans)
Per scan: ~$0.05      (Fargate compute — only charged when a scan runs)
Annual:   ~$144/year
```

---

*DocImgAnalizer — craftingnewtech.com*  
*Portfolio project — Option 2 (PoC) deployment.*
