# Docker Image Analyzer — PoC / Prototype Cost Analysis

**Date:** 2026-07-07  
**AWS Region:** us-east-1  
**Reference document:** `docs/InfrastructureCostAnalysis.md` (production baseline: ~$81/month)  
**Purpose:** Compare two lower-cost deployment options suitable for a prototype or PoC

---

## The Two Scenarios

| | Scenario A | Scenario B |
|-|-----------|-----------|
| **Name** | Single-AZ | PoC / Prototype |
| **Target use** | Dev/staging, cost-conscious production | Proof of concept, demos, early testing |
| **Architecture changes** | Minimal — same stack, one AZ | Significant — no VPC private networking, no WAF, no CMKs |
| **Monthly fixed cost** | **~$52/month** | **~$12/month** |
| **Production-ready?** | Yes (reduced availability) | No — security trade-offs documented below |

---

## Scenario A — Single-AZ

Same architecture as production. Only change: reduce from 2 availability zones to 1.

### What changes

```
environments/dev/terraform.tfvars

availability_zones = ["us-east-1a"]   # was ["us-east-1a", "us-east-1b"]
```

That single line cuts the VPC Interface Endpoint cost in half — from ~$58 to ~$29/month.
Everything else (VPC, private subnets, WAF, KMS CMKs, CloudWatch alarms) stays identical.

### Cost Breakdown — Single-AZ

**Phase 1**

| Service | Monthly Cost |
|---------|-------------|
| CloudFront | ~$2 |
| WAF (CloudFront) | ~$5 |
| API Gateway (HTTP API v2) | ~$0 |
| Lambda v1 | ~$0 |
| DynamoDB v1 | ~$1 |
| S3 (frontend + reports) | ~$1 |
| KMS CMKs (Phase 1 — 3 keys) | ~$3 |
| Route53 | ~$1 |
| CloudWatch | ~$2 |
| **Phase 1 Subtotal** | **~$15/month** |

**Phase 2**

| Service | Notes | Monthly Cost |
|---------|-------|-------------|
| VPC Interface Endpoints | 4 endpoints × **1 AZ** × $0.01/hr × 730 hrs | **~$29** |
| ECS Fargate (compute) | ~$0.05/scan at zero scans | ~$0 |
| ECR (image storage) | ~500 MB scanner image | ~$1 |
| Cognito | Free up to 50K MAUs | ~$0 |
| SQS | Free tier | ~$0 |
| DynamoDB v2 | On-demand | ~$1 |
| Lambda v2 | Free tier | ~$0 |
| KMS CMK (Phase 2) | 1 key | ~$1 |
| S3 (CVE + SBOM buckets) | | ~$1 |
| CloudWatch (Phase 2) | | ~$1 |
| **Phase 2 Subtotal** | | **~$34/month** |

**Phase 3**

| Service | Monthly Cost |
|---------|-------------|
| Secrets Manager (2 secrets) | ~$1 |
| DynamoDB v3 (3 tables) | ~$2 |
| Lambda v3 + Stripe webhook | ~$0 |
| EventBridge Scheduler | ~$0 |
| KMS CMK (Phase 3) | ~$1 |
| CloudWatch (Phase 3) | ~$1 |
| **Phase 3 Subtotal** | **~$4/month** |

### Single-AZ Total

```
Phase 1:  ~$15/month
Phase 2:  ~$34/month   ◄── VPC endpoints halved: $29 instead of $58
Phase 3:  ~$4/month
─────────────────────
Total:    ~$52/month   (zero subscribers)
```

**Saving vs. production:** ~$29/month

### Single-AZ Trade-offs

| Aspect | Impact |
|--------|--------|
| Availability | If `us-east-1a` has an outage, all Phase 2 deep scanning goes down |
| Data durability | DynamoDB and S3 are still replicated across AZs — no data loss risk |
| Recovery | Switch `terraform.tfvars` back to 2 AZs + `terraform apply` — ~10 min to restore |
| Suitable for | Dev, staging, early-stage production with SLA tolerance |
| Not suitable for | Production SLAs above 99.5% |

---

## Scenario B — PoC / Prototype

Fundamentally simplified architecture. Eliminates the three largest cost drivers:
**VPC Interface Endpoints**, **WAF**, and **KMS CMKs**.

### Architecture Changes

| Component | Production | PoC |
|-----------|-----------|-----|
| ECS Fargate networking | Private subnet, no internet | **Public subnet, `assignPublicIp = ENABLED`** |
| VPC Interface Endpoints | 4 Interface + 2 Gateway | **None — all removed** |
| WAF | CloudFront WebACL | **None — API Gateway throttling only** |
| Encryption keys | Customer-managed KMS CMKs (5 keys) | **AWS-managed keys (SSE-S3 + AWS-owned CMK)** |
| Availability zones | 2 | **1** |
| CloudWatch | Dashboards + alarms + logs | **Logs only** |
| SNS alerts | Yes | **None** |

### How Each Simplification Works

**1. Fargate in public subnet (eliminates $58/month in VPC endpoints)**

Instead of routing ECR pulls, SQS, and CloudWatch Logs through VPC Interface Endpoints,
the Fargate task is assigned a public IP and reaches AWS services over the internet.
Security is maintained by the **security group** — no inbound rules allowed; only outbound
HTTPS (port 443) is permitted to ECR, SQS, CloudWatch, and DynamoDB endpoints.

```hcl
# ECS task network config — PoC
awsvpcConfiguration = {
  subnets        = [public_subnet_id]
  securityGroups = [fargate_sg_id]
  assignPublicIp = "ENABLED"
}
```

**2. AWS-managed encryption (eliminates $5/month in CMK charges)**

S3 uses SSE-S3 (AES-256, AWS-managed). DynamoDB uses the AWS-owned CMK (free).
Lambda environment variables use the AWS-managed Lambda encryption key (free).
SQS uses the AWS-managed SQS key (free).

Trade-off: AWS holds the key, not you. For a PoC this is acceptable. For production with
compliance requirements (HIPAA, SOC2, etc.), CMKs are required.

**3. No WAF (eliminates $5/month)**

API Gateway HTTP API throttling replaces WAF for basic rate limiting:
- Steady-state: 100 requests/second
- Burst: 500 requests/second
- Per-client rate limit enforced via API keys (Phase 3)

Trade-off: No SQL injection protection, no geo-blocking, no IP reputation filtering.
Acceptable for a PoC with no real user data or payment processing.

**4. Single AZ (halves subnet and endpoint costs)**

One public subnet in `us-east-1a`. No private subnets needed.

### Cost Breakdown — PoC

**Phase 1**

| Service | Notes | Monthly Cost |
|---------|-------|-------------|
| CloudFront | | ~$2 |
| ~~WAF~~ | Removed | **$0** |
| API Gateway (HTTP API v2) | Throttling configured | ~$0 |
| Lambda v1 | Free tier | ~$0 |
| DynamoDB v1 | AWS-owned CMK (free encryption) | ~$1 |
| S3 (frontend) | SSE-S3 | ~$0.50 |
| S3 (reports) | SSE-S3 | ~$0.50 |
| ~~KMS CMKs~~ | Removed — AWS-managed keys | **$0** |
| Route53 | | ~$1 |
| CloudWatch | Logs only, no dashboards | ~$1 |
| **Phase 1 Subtotal** | | **~$6/month** |

**Phase 2**

| Service | Notes | Monthly Cost |
|---------|-------|-------------|
| ~~VPC Interface Endpoints~~ | Removed — Fargate uses public subnet | **$0** |
| VPC (public subnet only) | Minimal — no NAT, no endpoints | ~$0 |
| ECS Fargate (compute) | ~$0.05/scan at zero scans | ~$0 |
| ECR (image storage) | ~500 MB | ~$1 |
| Cognito | Free up to 50K MAUs | ~$0 |
| SQS | Free tier | ~$0 |
| DynamoDB v2 | AWS-owned CMK | ~$1 |
| Lambda v2 | Free tier | ~$0 |
| S3 (CVE + SBOM) | SSE-S3 | ~$1 |
| CloudWatch | Logs only | ~$1 |
| **Phase 2 Subtotal** | | **~$4/month** |

**Phase 3**

| Service | Notes | Monthly Cost |
|---------|-------|-------------|
| Secrets Manager | Stripe keys — $0.40/secret × 2 | ~$1 |
| DynamoDB v3 | 3 tables, AWS-owned CMK | ~$1 |
| Lambda v3 + Stripe webhook | Free tier | ~$0 |
| EventBridge Scheduler | 1 rule | ~$0 |
| CloudWatch | Logs only | ~$0.50 |
| **Phase 3 Subtotal** | **~$2.50/month** | |

### PoC Total

```
Phase 1:  ~$6/month
Phase 2:  ~$4/month   ◄── $0 VPC endpoints (biggest saving)
Phase 3:  ~$3/month
─────────────────────
Total:    ~$12/month  (zero subscribers)
```

**Saving vs. production:** ~$69/month  
**Saving vs. Single-AZ:** ~$40/month

---

## Side-by-Side Comparison

| | Production | Scenario A: Single-AZ | Scenario B: PoC |
|-|-----------|----------------------|----------------|
| **Fixed monthly cost** | **~$81** | **~$52** | **~$12** |
| **Saving vs. production** | — | ~$29/month | ~$69/month |
| **AZs** | 2 | 1 | 1 |
| **VPC Interface Endpoints** | 4 × 2 AZ ($58) | 4 × 1 AZ ($29) | None ($0) |
| **WAF** | Yes ($5) | Yes ($5) | No ($0) |
| **KMS CMKs** | 5 × $1 ($5) | 5 × $1 ($5) | None ($0) |
| **CloudWatch dashboards** | Yes | Yes | No |
| **CloudWatch alarms** | Yes | Yes | No |
| **SNS alerts** | Yes | Yes | No |
| **Fargate networking** | Private subnet | Private subnet | Public subnet |
| **Encryption** | CMK (you hold the key) | CMK (you hold the key) | AWS-managed |
| **HA / Multi-AZ** | Yes | No | No |
| **DDoS protection** | WAF + CloudFront | WAF + CloudFront | CloudFront + throttling |
| **Production-ready** | Yes | Partial | No |
| **Good for PoC/demo** | Overkill | Yes | Yes — lowest cost |

---

## Break-Even at PoC Pricing

At $12/month fixed cost, the economics are dramatically better:

| Subscribers | Revenue | AWS Cost | Stripe Fees | Net |
|------------|---------|----------|-------------|-----|
| 0 | $0 | ~$12 | $0 | -$12 |
| 1 Pro | $19 | ~$12 | ~$0.85 | **+$6.15** |
| 3 Pro | $57 | ~$13 | ~$2.55 | **+$41.45** |
| 1 Enterprise | $99 | ~$12 | ~$3.17 | **+$83.83** |

Break-even at **1 Pro subscriber** — the PoC pays for itself almost immediately.

---

## Recommended Migration Path: PoC → Production

Start with Scenario B (PoC) to validate product-market fit with minimal burn. Migrate to
production architecture when paying subscribers justify the cost.

```
PoC (~$12/month)
  │
  │  Trigger: First 5 paying subscribers (~$95 revenue/month)
  ▼
Single-AZ (~$52/month)
  │
  │  Trigger: Sustained revenue > $200/month OR enterprise customer onboarded
  ▼
Production / Multi-AZ (~$81/month)
```

### What needs to change at each step

**PoC → Single-AZ:**
1. Add second AZ in `terraform.tfvars`
2. Add VPC Interface Endpoints (4 endpoints)
3. Move Fargate tasks to private subnet (remove `assignPublicIp`)
4. Add WAF WebACL
5. `terraform apply` — ~15 min

**Single-AZ → Production:**
1. Add second AZ in `terraform.tfvars` → apply
2. Replace AWS-managed encryption with CMKs (if PoC chose Scenario B)
3. Enable CloudWatch dashboards and alarms
4. `terraform apply` — ~20 min

No application code changes required at any step — only Terraform configuration.

---

## PoC Security Risks — Acknowledged

These risks are acceptable for a PoC/demo environment with no real user PII or payment data.
They must be resolved before going to production.

| Risk | Severity | Mitigation in PoC | Required fix for prod |
|------|----------|------------------|----------------------|
| Fargate task has public IP | Medium | SG blocks all inbound; outbound scoped to port 443 | Move to private subnet + VPC endpoints |
| No WAF | Medium | API GW throttling limits burst abuse | Add WAF WebACL |
| AWS-managed encryption keys | Low | Data is still encrypted at rest | Replace with CMKs |
| Single AZ | Low | Acceptable downtime for PoC | Add second AZ |
| No CloudWatch alarms | Low | Manual monitoring sufficient for PoC | Add alarms before prod |

---

*DocImgAnalizer — craftingnewtech.com*  
*Cost data based on AWS us-east-1 public pricing as of 2026-07-07.*
