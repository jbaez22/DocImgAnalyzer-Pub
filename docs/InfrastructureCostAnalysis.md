# Docker Image Analyzer — Infrastructure Cost Analysis

**Date:** 2026-07-07  
**AWS Region:** us-east-1  
**Scope:** Full system cost after Phase 1 + Phase 2 + Phase 3 are deployed  
**Pricing basis:** AWS public pricing (no Reserved Instances, no Savings Plans)

---

## Summary

| Phase | Fixed Monthly Cost | Notes |
|-------|--------------------|-------|
| Phase 1 | ~$15 | CloudFront, WAF, Lambda v1, DynamoDB v1, KMS |
| Phase 2 | ~$62 | VPC Interface Endpoints dominate (~$58) |
| Phase 3 | ~$4 | Secrets Manager, DynamoDB v3 |
| **Total (zero subscribers)** | **~$81/month** | Fixed infrastructure floor |

---

## Phase 1 Cost Breakdown

| Service | Configuration | Unit Price | Monthly Cost |
|---------|--------------|-----------|--------------|
| CloudFront | Minimal traffic, US/EU | $0.0085/10K requests | ~$2 |
| WAF (CloudFront) | 1 WebACL + rules | $5/WebACL + $1/10M requests | ~$5 |
| API Gateway (HTTP API v2) | Low traffic | $1.00/million requests | ~$0 |
| Lambda v1 | 128–512 MB, <1M invocations/month | Free tier covers | ~$0 |
| DynamoDB v1 | On-Demand, `img-analyzer-{env}-scans` | $1.25/million RCU + WCU | ~$1 |
| S3 (frontend bucket) | Static assets, <1 GB | $0.023/GB + request costs | ~$0.50 |
| S3 (reports bucket) | Scan reports, <1 GB | $0.023/GB + request costs | ~$0.50 |
| KMS CMKs | 3 keys (DynamoDB, S3 reports, Lambda env) | $1.00/key/month | ~$3 |
| Route53 | 1 hosted zone | $0.50/zone/month | ~$1 |
| CloudWatch | Logs + 4 alarms + 1 dashboard | $0.30/GB logs + $0.10/alarm | ~$2 |
| SNS | Alert notifications | 1M notifications free | ~$0 |
| ACM (TLS certificates) | Wildcard cert | Free | $0 |
| **Phase 1 Subtotal** | | | **~$15/month** |

---

## Phase 2 Cost Breakdown

### VPC Interface Endpoints — Cost Driver

| Endpoint | Type | AZs | Hours/month | $/hr/AZ | Monthly Cost |
|----------|------|-----|-------------|---------|--------------|
| ECR API (`ecr.api`) | Interface | 2 | 730 | $0.01 | ~$14.60 |
| ECR DKR (`ecr.dkr`) | Interface | 2 | 730 | $0.01 | ~$14.60 |
| SQS (`sqs`) | Interface | 2 | 730 | $0.01 | ~$14.60 |
| CloudWatch Logs (`logs`) | Interface | 2 | 730 | $0.01 | ~$14.60 |
| S3 | Gateway | — | — | Free | $0 |
| DynamoDB | Gateway | — | — | Free | $0 |
| **Interface Endpoint Subtotal** | | | | | **~$58.40/month** |

> **Why Interface endpoints?** ECS Fargate tasks run in private subnets with no internet
> access — no NAT Gateway, no public IPs. All AWS service traffic must route through VPC
> endpoints. This is the correct security architecture. The 4 Interface endpoints are
> required for ECR image pulls, SQS polling, and CloudWatch Logs.

### Other Phase 2 Services

| Service | Configuration | Unit Price | Monthly Cost |
|---------|--------------|-----------|--------------|
| ECS Fargate (compute) | 0.5 vCPU / 1 GB RAM per scan task | $0.04048/vCPU-hr + $0.004445/GB-hr | ~$0.05/scan |
| ECR (image storage) | Scanner image ~500 MB | $0.10/GB/month | ~$0.05 |
| Cognito User Pool | Free up to 50,000 MAUs | $0.0055/MAU after 50K | ~$0 |
| SQS (scan queue + DLQ) | <1M requests/month | 1M requests free tier | ~$0 |
| DynamoDB v2 | On-Demand, `img-analyzer-{env}-scans-v2` | $1.25/million RCU + WCU | ~$1 |
| Lambda v2 | FastAPI, <1M invocations/month | Free tier covers | ~$0 |
| KMS CMK (Phase 2) | 1 key for DynamoDB v2, SQS, S3 buckets | $1.00/key/month | ~$1 |
| S3 (CVE reports bucket) | Scan JSON reports | $0.023/GB | ~$0.50 |
| S3 (SBOM reports bucket) | CycloneDX JSON files | $0.023/GB | ~$0.50 |
| CloudWatch (Phase 2) | Logs + alarms + dashboard | $0.30/GB logs | ~$1 |
| **Phase 2 Subtotal** | | | **~$62/month** |

---

## Phase 3 Cost Breakdown

| Service | Configuration | Unit Price | Monthly Cost |
|---------|--------------|-----------|--------------|
| Secrets Manager | 2 secrets (Stripe secret key + webhook signing secret) | $0.40/secret/month | ~$1 |
| DynamoDB v3 | 3 tables: subscriptions, api-keys, orgs (On-Demand) | $1.25/million RCU + WCU | ~$2 |
| Lambda v3 | FastAPI v3, entitlement middleware | Free tier covers | ~$0 |
| Lambda (Stripe webhook) | Event-driven, low invocation count | Free tier covers | ~$0 |
| Lambda (EventBridge re-scan) | 1 invocation/day | Free tier covers | ~$0 |
| EventBridge Scheduler | 1 rule, daily at 02:00 UTC | $0.00864/rule/month | ~$0 |
| KMS CMK (Phase 3) | 1 key for DynamoDB v3 + Secrets Manager | $1.00/key/month | ~$1 |
| CloudWatch (Phase 3) | Dashboard + Stripe webhook alarms | $0.30/GB logs | ~$1 |
| **Phase 3 Subtotal** | | | **~$4/month** |

---

## Total Fixed Infrastructure Cost

```
Phase 1:  ~$15/month
Phase 2:  ~$62/month   ◄── VPC Interface Endpoints: $58.40 of this
Phase 3:  ~$4/month
─────────────────────
Total:    ~$81/month   (zero subscribers, zero scan traffic)
```

---

## Variable Costs — Usage-Based

These costs increase with usage:

| Variable | Unit Cost | Example: 100 scans/mo | Example: 500 scans/mo | Example: 2,000 scans/mo |
|----------|-----------|----------------------|----------------------|-------------------------|
| ECS Fargate (deep scan) | ~$0.05/scan | ~$5 | ~$25 | ~$100 |
| S3 storage (reports) | $0.023/GB | ~$0.50 | ~$2 | ~$8 |
| DynamoDB read/write | $1.25/million | ~$0 | ~$0.50 | ~$2 |
| CloudFront data transfer | $0.085/GB (first 10 TB) | ~$0.50 | ~$2 | ~$8 |
| **Variable subtotal** | | **~$6** | **~$30** | **~$118** |

---

## Total Monthly Cost at Different Usage Levels

| Subscribers | Scans/month | Fixed Cost | Variable Cost | AWS Total | Stripe Fees (2.9%+$0.30) | Net Revenue |
|------------|------------|-----------|--------------|-----------|--------------------------|-------------|
| 0 | 0 | ~$81 | $0 | **~$81** | $0 | **-$81** |
| 5 Pro | ~100 | ~$81 | ~$6 | **~$87** | ~$3 | **+$5** |
| 10 Pro | ~200 | ~$81 | ~$11 | **~$92** | ~$6 | **+$92** |
| 20 Pro | ~400 | ~$81 | ~$21 | **~$102** | ~$12 | **+$266** |
| 5 Pro + 2 Enterprise | ~300 | ~$81 | ~$16 | **~$97** | ~$9 | **+$187** |
| 20 Pro + 5 Enterprise | ~900 | ~$81 | ~$46 | **~$127** | ~$26 | **+$722** |
| 50 Pro + 10 Enterprise | ~2,000 | ~$81 | ~$118 | **~$199** | ~$62 | **+$1,729** |

> **Revenue formula:** (Pro subscribers × $19) + (Enterprise subscribers × $99) − AWS cost − Stripe fees

---

## Break-Even Analysis

| Break-even point | Subscribers needed |
|-----------------|--------------------|
| Cover Phase 2 VPC endpoints alone ($58) | 4 Pro subscribers |
| Cover total AWS fixed cost ($81) | 5 Pro subscribers |
| Cover AWS + Stripe fees at typical usage | 6 Pro subscribers |

**Break-even is very low** — 5–6 Pro subscribers covers the entire infrastructure.
At 10 Pro subscribers the service is cash-flow positive by ~$90/month.

---

## The VPC Interface Endpoint Problem

VPC Interface Endpoints are the largest single cost at **~$58/month (72% of fixed costs)**.

### Why they are required (current architecture)
- Fargate scanner tasks run in **private subnets** with no internet access
- Private subnet = no public IP, no NAT Gateway
- ECR image pulls, SQS polling, and CloudWatch Logs must route through VPC endpoints
- This is the correct zero-egress security architecture

### Alternatives and trade-offs

| Option | Monthly Cost | Saving vs. Current | Security Impact |
|--------|-------------|-------------------|----------------|
| **Current (4 Interface endpoints)** | **~$58** | — | Best — no internet egress |
| Replace with NAT Gateway (2 AZs) | ~$67 | -$9 more expensive | Good — still private, but NAT is single egress point |
| Replace with NAT Gateway (1 AZ) | ~$34 | +$24 saving | Acceptable — single point of failure |
| Single AZ Interface endpoints | ~$29 | +$29 saving | Good — availability risk only |
| Public subnet (assign public IP) | ~$0 | +$58 saving | Poor — scanner has internet exposure |

### Recommendation
Keep current architecture for **production**. For the **dev environment**, consider reducing
to a single AZ to save ~$29/month while Phase 3 is in development:

```hcl
# environments/dev/terraform.tfvars
availability_zones = ["us-east-1a"]   # single AZ for dev cost savings
```

This would reduce dev environment cost from ~$81 to ~$52/month.

---

## KMS Key Cost Summary

KMS charges $1.00/month per CMK (customer-managed key) plus $0.03/10,000 API calls.

| Key | Phase | Used by | Monthly Cost |
|-----|-------|---------|--------------|
| Phase 1 CMK | Phase 1 | DynamoDB v1, S3 reports, Lambda v1 env vars | $1 |
| Phase 1 SNS CMK | Phase 1 | SNS encryption | $1 |
| Phase 1 Artifacts CMK | Phase 1 | S3 artifacts bucket | $1 |
| Phase 2 CMK | Phase 2 | DynamoDB v2, SQS, S3 phase2 buckets, Lambda v2 | $1 |
| Phase 3 CMK | Phase 3 | DynamoDB v3, Secrets Manager | $1 |
| **KMS Total** | | | **~$5/month** |

---

## Cost Reduction Opportunities

| Opportunity | Potential Saving | Effort | When to do it |
|-------------|-----------------|--------|---------------|
| Consolidate KMS keys (share one CMK across phases) | ~$3/month | Low | Phase 3 security hardening |
| Single-AZ dev environment | ~$29/month (dev only) | Low | Before Phase 3 starts |
| DynamoDB reserved capacity (after traffic is stable) | 20–30% DDB saving | Low | Post Phase 3 launch |
| Lambda memory right-sizing (after profiling) | Minimal | Low | Post launch |
| S3 Intelligent-Tiering for old reports | Minimal at low volume | Low | When reports > 10 GB |
| Reserved Concurrency / Provisioned Concurrency | Neutral or negative at low traffic | — | Only if cold starts are a problem |

---

## Stripe Fee Reference

Stripe charges **2.9% + $0.30 per successful transaction** (standard pricing).

| Transaction | Gross Revenue | Stripe Fee | Net Revenue |
|------------|---------------|-----------|-------------|
| 1 Pro subscription ($19) | $19.00 | $0.85 | $18.15 |
| 1 Enterprise subscription ($99) | $99.00 | $3.17 | $95.83 |
| 10 Pro subscriptions | $190.00 | $8.50 | $181.50 |
| 5 Enterprise subscriptions | $495.00 | $15.85 | $479.15 |

---

## IAM Access Analyzer Cost

Two analyzers are running as of 2026-07-07:

| Analyzer | Type | Cost |
|----------|------|------|
| `docimganalyzer-external-access` | ACCOUNT (external access) | Free |
| `docimganalyzer-unused-access` | ACCOUNT_UNUSED_ACCESS | $0.20/IAM role/month |

**Current account IAM roles:** 53  
**Unused access analyzer cost:** 53 × $0.20 = **~$10.60/month** (prorated)  
**Action required ~2026-07-12:** Delete `docimganalyzer-unused-access` after reviewing findings.  
**Keep permanently:** `docimganalyzer-external-access` (free — detects accidental public access).

---

## Projected 12-Month Cost (Infrastructure Only)

Assuming Phase 3 launches in Month 1 and subscriber growth is conservative:

| Month | Pro Subs | Ent. Subs | AWS Cost | Revenue | Net |
|-------|----------|-----------|----------|---------|-----|
| 1 | 0 | 0 | ~$81 | $0 | -$81 |
| 2 | 2 | 0 | ~$83 | $38 | -$45 |
| 3 | 5 | 0 | ~$87 | $95 | +$8 |
| 4 | 8 | 1 | ~$89 | $251 | +$162 |
| 6 | 15 | 2 | ~$96 | $483 | +$387 |
| 9 | 25 | 4 | ~$110 | $871 | +$761 |
| 12 | 40 | 6 | ~$130 | $1,354 | +$1,224 |

> Conservative estimate — assumes slow organic growth and no marketing spend.
> Break-even reached at Month 3 (5 Pro subscribers).

---

*DocImgAnalizer — craftingnewtech.com*  
*Cost data based on AWS us-east-1 public pricing as of 2026-07-07.*  
*Actual costs may vary based on traffic, data transfer, and AWS pricing changes.*
