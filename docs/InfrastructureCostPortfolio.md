# Docker Image Analyzer — Portfolio Project Cost Analysis

**Date:** 2026-07-07  
**Purpose:** Monthly cost breakdown for a portfolio / showcase deployment  
**Goal:** Keep the live demo running at minimum cost while demonstrating maximum technical depth  
**Reference:** `docs/InfrastructureCostAnalysis.md` (production baseline: ~$81/month)

---

## Context

This project is a **portfolio piece for job interviews**, not a commercial product.
There is no revenue to offset AWS costs — every dollar spent comes out of pocket.

The goal is to have a **live, working demo** at the lowest possible cost while still
demonstrating a credible, production-grade architecture in the code and documentation.

Key principle: **the code shows you know how to do it right; the infrastructure shows
you know how to be cost-conscious.** Both are interview-worthy signals.

---

## The Two Portfolio Options

| | Option 1: Single-AZ | Option 2: PoC |
|-|--------------------|-----------------------------|
| **Monthly cost** | **~$52/month** | **~$12/month** |
| **Annual cost** | **~$624/year** | **~$144/year** |
| **Architecture** | Full production stack, 1 AZ | Simplified — no VPC endpoints, no WAF, no CMKs |
| **What it shows interviewers** | You built the real thing and chose to reduce AZs deliberately | You understand trade-offs and can architect for cost constraints |
| **Live demo quality** | Identical to production | Identical to production (users cannot tell the difference) |
| **Recommended for** | If budget allows | **Recommended — best value for a portfolio** |

---

## Option 1 — Single-AZ Portfolio (~$52/month)

Full production architecture with one availability zone.
Same stack as production — VPC private subnets, WAF, KMS CMKs, CloudWatch alarms.
Only difference from full production: single AZ reduces VPC Interface Endpoint cost by half.

### Monthly Breakdown

| Phase | Service | Monthly Cost |
|-------|---------|-------------|
| **Phase 1** | CloudFront | ~$2 |
| | WAF (CloudFront WebACL) | ~$5 |
| | API Gateway + Lambda v1 | ~$0 |
| | DynamoDB v1 | ~$1 |
| | S3 (frontend + reports) | ~$1 |
| | KMS CMKs (3 keys) | ~$3 |
| | Route53 | ~$1 |
| | CloudWatch (logs + alarms) | ~$2 |
| | **Phase 1 Subtotal** | **~$15** |
| **Phase 2** | VPC Interface Endpoints (4 × 1 AZ) | ~$29 |
| | ECS Fargate (at zero scans) | ~$0 |
| | ECR, SQS, Cognito, DynamoDB v2 | ~$2 |
| | KMS CMK (Phase 2) | ~$1 |
| | S3 (CVE + SBOM buckets) | ~$1 |
| | CloudWatch | ~$1 |
| | **Phase 2 Subtotal** | **~$34** |
| **Phase 3** | Secrets Manager (Stripe test keys) | ~$1 |
| | DynamoDB v3 (3 tables) | ~$2 |
| | Lambda v3 + EventBridge | ~$0 |
| | KMS CMK (Phase 3) | ~$1 |
| | CloudWatch | ~$1 |
| | **Phase 3 Subtotal** | **~$4** |
| | | |
| | **TOTAL** | **~$52/month** |

### What this demonstrates to interviewers

- Production-grade VPC private networking with Interface Endpoints
- WAF integration with CloudFront
- KMS CMK encryption across all data stores
- Multi-module Terraform with separate state per phase
- Conscious decision to use single AZ for cost — documented in `InfrastructureCostAnalysis.md`

---

## Option 2 — PoC Portfolio (~$12/month) ✓ Recommended

Simplified architecture that cuts the three biggest cost drivers.
**The live demo looks and behaves identically** — users and interviewers cannot tell
the difference. The architectural trade-offs are documented in code and docs,
which is itself an interview talking point.

### Monthly Breakdown

| Phase | Service | Notes | Monthly Cost |
|-------|---------|-------|-------------|
| **Phase 1** | CloudFront | | ~$2 |
| | ~~WAF~~ | Removed — API GW throttling instead | $0 |
| | API Gateway + Lambda v1 | | ~$0 |
| | DynamoDB v1 | AWS-managed encryption | ~$1 |
| | S3 (frontend + reports) | SSE-S3 | ~$1 |
| | ~~KMS CMKs~~ | Removed — AWS-managed keys | $0 |
| | Route53 | | ~$1 |
| | CloudWatch (logs only) | No dashboards for PoC | ~$1 |
| | **Phase 1 Subtotal** | | **~$6** |
| **Phase 2** | ~~VPC Interface Endpoints~~ | Removed — Fargate uses public subnet | $0 |
| | ECS Fargate (at zero scans) | | ~$0 |
| | ECR, SQS, Cognito, DynamoDB v2 | | ~$2 |
| | S3 (CVE + SBOM buckets) | SSE-S3 | ~$1 |
| | CloudWatch (logs only) | | ~$1 |
| | **Phase 2 Subtotal** | | **~$4** |
| **Phase 3** | Secrets Manager (Stripe test keys) | | ~$1 |
| | DynamoDB v3 (3 tables) | | ~$1 |
| | Lambda v3 + EventBridge | | ~$0 |
| | CloudWatch | | ~$0.50 |
| | **Phase 3 Subtotal** | | **~$2.50** |
| | | | |
| | **TOTAL** | | **~$12/month** |

### What this demonstrates to interviewers

- You understand where costs come from and made a deliberate trade-off decision
- The `InfrastructureCostAnalysis.md` and `InfrastructureCostAnalysisPoC.md` docs
  prove you analyzed the options — most engineers don't do this
- The code for WAF, KMS CMKs, and VPC private networking **still exists** in
  `terraform/phase1/` and `terraform/phase2/` — interviewers can see the full
  production architecture in the code even though it isn't deployed that way

---

## Annual Cost Comparison

| Option | Monthly | Annual | Saving vs. Production |
|--------|---------|--------|----------------------|
| Production (full) | ~$81 | ~$972 | — |
| Option 1: Single-AZ | ~$52 | ~$624 | ~$348/year |
| **Option 2: PoC** | **~$12** | **~$144** | **~$828/year** |

---

## Phase 3 — Stripe in Test Mode

For a portfolio project, Stripe runs in **test mode only**:

- Use `sk_test_*` and `pk_test_*` keys from the Stripe Dashboard
- Payments use [Stripe test cards](https://stripe.com/docs/testing) — no real money moves
- The checkout flow, webhooks, and entitlement updates all work exactly the same
- The Stripe Dashboard shows all test transactions — useful for demos

**What to tell an interviewer:**
> "Stripe is running in test mode — I can walk you through a full checkout flow using a
> test card right now. The production switch is a single config change — swap the test
> keys for live keys in Secrets Manager."

This is a completely honest and professional answer. Many SaaS demos run in test mode.

---

## Variable Costs (Usage-Based)

Both options share the same variable costs per scan:

| Usage | Additional Cost/month |
|-------|-----------------------|
| 10 deep scans | ~$0.50 (Fargate compute) |
| 50 deep scans | ~$2.50 |
| 100 deep scans | ~$5 |

For a portfolio demo with occasional interview use, expect fewer than 20 scans/month — essentially zero additional cost.

---

## Recommendation

**Use Option 2 (PoC, ~$12/month).**

The $40/month difference between the two options ($480/year) is not justified for a
portfolio project with no revenue. The demo is identical. The architectural knowledge
is visible in the code and documentation regardless of which infrastructure is deployed.

The cost analysis documents you now have (`InfrastructureCostAnalysis.md`,
`InfrastructureCostAnalysisPoC.md`, this file) are themselves portfolio artifacts —
they show an interviewer that you think about cost as a first-class engineering concern,
not an afterthought.

### Terraform change required to switch from current to Option 2

The current dev deployment is Option 1 (Single-AZ, VPC with Interface Endpoints).
To move to Option 2:

```hcl
# terraform/phase2/environments/dev/terraform.tfvars
availability_zones = ["us-east-1a"]        # already single AZ — no change needed

# terraform/phase2/modules/vpc/main.tf
# Comment out the 4 Interface endpoint resources (ecr_api, ecr_dkr, sqs, logs)
# Change ECS task assignPublicIp = "ENABLED", move to public subnet
```

This is a Phase 3 infrastructure decision — current Phase 2 dev is already deployed
and working. Evaluate cost vs. convenience before making the change.

---

*DocImgAnalizer — craftingnewtech.com*  
*Portfolio project — not a commercial product.*
