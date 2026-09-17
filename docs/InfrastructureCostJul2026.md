# Infrastructure Cost Analysis — July 2026

Current state: Phase 1 + Phase 2 + Phase 3 fully deployed in **dev** and **prod**.
Data source: AWS Cost Explorer, account-wide + resource enumeration, 2026-07-09.

---

## Cost Summary — PoC Optimization Journey

The optimization attempt (move scanner image from ECR to Docker Hub) failed because
Fargate tasks in this VPC cannot reach the public internet reliably. The fix required
adding back the ECR endpoints PLUS a new CloudWatch Logs endpoint — a net cost increase
of ~$14/month. The final fix replaces all three Interface Endpoints with a single NAT
Gateway, giving full internet access AND saving ~$12/month vs the 3-endpoint state.

```
┌─────────────────────────────────────────────────────┬──────────────┬──────────────┬──────────────┐
│ Resource                                            │ Original     │ +CW Logs EP  │ NAT GW (now) │
├─────────────────────────────────────────────────────┼──────────────┼──────────────┼──────────────┤
│ Always-on (WAF, KMS, Route 53, Secrets Manager)     │   $20.20     │   $20.20     │   $20.20     │
│ ECR API + DKR + CW Logs endpoints (dev + prod)      │   $29.20     │   $43.80     │    $0.00     │
│ NAT Gateway + EIP (dev + prod)          ← NEW       │    $0.00     │    $0.00     │   $32.00     │
│ Pay-per-use (Lambda, ECS scans, etc.)               │    $0.22     │    $0.22     │    $0.22     │
├─────────────────────────────────────────────────────┼──────────────┼──────────────┼──────────────┤
│ MONTHLY TOTAL                                       │  ~$49.60     │  ~$64.00     │  ~$52.00     │
└─────────────────────────────────────────────────────┴──────────────┴──────────────┴──────────────┘
```

**Why NAT Gateway wins:** Three VPC Interface Endpoints ($43.80/month) only covered specific
AWS services — Trivy still couldn't reach Docker Hub to pull target scan images. A NAT
Gateway ($32/month) provides full outbound internet, fixes the Trivy timeout, AND costs
less. Fargate tasks now run in a **private subnet** with `AssignPublicIp=DISABLED`; the
NAT GW sits in the public subnet.

---

## AWS Account Context

This account hosts multiple projects. July month-to-date total (9 days) was **$24.92**,
but several line items belong to other projects:

```
┌─────────────────────────┬──────────────┬──────────────────────────────────────────────┐
│ Service                 │ MTD (9 days) │ Owner                                        │
├─────────────────────────┼──────────────┼──────────────────────────────────────────────┤
│ AWS WAF                 │    $8.31     │ Shared — 5 WebACLs; 2 are DocImgAnalizer     │
│ IAM Access Analyzer     │    $6.40     │ Other project                                │
│ Amazon VPC              │    $3.20     │ Other project                                │
│ Amazon Route 53         │    $2.51     │ Shared — 5 hosted zones; 1 is DocImgAnalizer │
│ Tax                     │    $1.38     │ Proportional                                 │
│ EC2 - Other             │    $1.15     │ Other project (no NAT Gateway here)          │
│ KMS                     │    $0.61     │ DocImgAnalizer (6 CMK keys)                  │
│ RDS                     │    $0.55     │ Other project (no RDS here)                  │
│ S3                      │    $0.48     │ Shared                                       │
│ Secrets Manager         │    $0.12     │ DocImgAnalizer + 1 other project             │
│ ECS                     │    $0.01     │ DocImgAnalizer                               │
│ ECR                     │    $0.01     │ DocImgAnalizer                               │
│ DynamoDB                │    $0.00     │ DocImgAnalizer                               │
│ API Gateway             │    $0.00     │ DocImgAnalizer                               │
└─────────────────────────┴──────────────┴──────────────────────────────────────────────┘
```

---

## DocImgAnalizer Monthly Cost — Current State

### Always-On Resources

```
┌──────────────────────────────────────────────────┬───────┬──────────────────┬──────────┐
│ Resource                                         │ Count │ Unit Cost        │ Monthly  │
├──────────────────────────────────────────────────┼───────┼──────────────────┼──────────┤
│ KMS Customer Managed Keys                        │   6   │ $1.00 / key      │  $6.00   │
│ WAF WebACL (CloudFront scope)                    │   2   │ $5.00 / ACL      │ $10.00   │
│ WAF rate-based rule (RateLimitPerIP)             │   2   │ $1.00 / rule     │  $2.00   │
│ AWS Managed WAF rules (CommonRuleSet + BadInput) │   4   │ Free             │  $0.00   │
│ Secrets Manager (Stripe keys — dev + prod)       │   4   │ $0.40 / secret   │  $1.60   │
│ Route 53 hosted zone (craftingnewtech.com)       │   1   │ $0.50 / zone     │  $0.50   │
│ Cognito User Pools (dev + prod)                  │   2   │ Free ≤ 50K MAU   │  $0.00   │
│ ECR repositories (dev + prod)                    │   2   │ ~$0.05 storage   │  $0.10   │
│ CloudFront distribution                          │   1   │ Free ≤ 1 TB/mo   │  $0.00   │
│ ACM certificates                                 │   2   │ Free             │  $0.00   │
├──────────────────────────────────────────────────┼───────┼──────────────────┼──────────┤
│ Always-on subtotal                               │       │                  │ $20.20   │
└──────────────────────────────────────────────────┴───────┴──────────────────┴──────────┘
```

### VPC Networking (always-on)

```
┌──────────────────────────────────────────┬──────────────┬────────────────────┬──────────┐
│ Resource                                 │ Environments │ Unit Cost          │ Monthly  │
├──────────────────────────────────────────┼──────────────┼────────────────────┼──────────┤
│ NAT Gateway                              │ dev + prod   │ $0.045/hr × 730 hr │  $32.00  │
│ Elastic IP (attached to NAT GW)          │ dev + prod   │ Free while attached│  $0.00   │
├──────────────────────────────────────────┼──────────────┼────────────────────┼──────────┤
│ VPC networking subtotal                  │              │                    │  $32.00  │
└──────────────────────────────────────────┴──────────────┴────────────────────┴──────────┘
```

> Note: S3 and DynamoDB use **Gateway** endpoints (free) — kept in place alongside NAT GW.
> The three VPC Interface Endpoints (ECR API, ECR DKR, CloudWatch Logs) have been removed.

### Pay-Per-Use (negligible at portfolio traffic levels)

```
┌────────────────────────────────────────────┬───────────────────────────┬───────────┐
│ Resource                                   │ Free Tier                 │ Est./month│
├────────────────────────────────────────────┼───────────────────────────┼───────────┤
│ Lambda (v1 + v2 + v3 functions)            │ 1M requests/mo free       │   $0.00   │
│ API Gateway HTTP API                       │ 1M calls/mo free          │   $0.01   │
│ DynamoDB (4 tables, on-demand)             │ 25 GB + 25 RCU/WCU free   │   $0.01   │
│ S3 (frontend + reports + SBOM buckets)     │ 5 GB + 20K GET free       │   $0.05   │
│ ECS Fargate (per scan, ~30s, 0.5vCPU/1GB)  │ Pay per use               │   $0.05   │
│ SQS queues                                 │ 1M requests/mo free       │   $0.00   │
│ EventBridge Pipes                          │ 10M events/mo free        │   $0.00   │
│ CloudWatch Logs (log ingestion)            │ ~$0.50/GB ingested        │   $0.10   │
│ SNS                                        │ 1M publishes/mo free      │   $0.00   │
├────────────────────────────────────────────┼───────────────────────────┼───────────┤
│ Pay-per-use subtotal                       │                           │   $0.22   │
└────────────────────────────────────────────┴───────────────────────────┴───────────┘
```

### Monthly Total

```
  Always-on resources   $20.20
  NAT Gateway (2 envs)  $32.00
  Pay-per-use            $0.22
  ─────────────────────────────
  TOTAL                ~$52.00 / month
```

---

## Cost Reduction Options

### Option A — Remove WAF from dev environment

The dev WAF WebACL provides no real security value at portfolio traffic levels.
Keeping WAF only in prod still demonstrates the architecture for demos.

```
  WAF WebACL (dev)           -$5.00
  WAF rate-based rule (dev)  -$1.00
  ─────────────────────────────────
  Savings                    -$6.00/month  →  new total ~$58/month
```

### Option B — Consolidate KMS keys

Six CMK keys across three phases and two environments. Could share one key per
environment instead of one per phase.

```
  Current  :  6 keys × $1.00 = $6.00/month
  After    :  2 keys × $1.00 = $2.00/month
  ─────────────────────────────────────────
  Savings                    -$4.00/month  →  new total ~$60/month
```

Risk: high implementation effort for limited savings; one CMK per phase is correct
security practice (separate blast radius) and reads well in portfolio demos.
**Not recommended.**

### Options A + B combined

```
  WAF savings (dev only)     -$6.00
  KMS consolidation          -$4.00
  ─────────────────────────────────
  Combined savings          -$10.00/month  →  new total ~$54/month
```

---

## Scenario Comparison

```
┌──────────────────────────────────────────────────────┬──────────────┬──────────────────────────────────┐
│ Scenario                                             │ Monthly Cost │ Notes                            │
├──────────────────────────────────────────────────────┼──────────────┼──────────────────────────────────┤
│ 3 VPC Interface Endpoints (previous — broken Trivy)  │   ~$64/month │ Trivy couldn't reach Docker Hub  │
│ NAT Gateway (current — Trivy works)                  │   ~$52/month │ Full internet, ~$12 cheaper      │
│ NAT GW + Option A (remove dev WAF)                   │   ~$46/month │ Low effort, safe change          │
│ NAT GW + Options A + B (remove dev WAF + merge KMS)  │   ~$42/month │ Higher effort, limited gain      │
└──────────────────────────────────────────────────────┴──────────────┴──────────────────────────────────┘
```

---

## Resource Inventories

### KMS Customer Managed Keys

```
┌─────────────────────────────────────────────────────────────────┬─────────┬───────┐
│ Key Description                                                 │ Env     │ Phase │
├─────────────────────────────────────────────────────────────────┼─────────┼───────┤
│ CMK for img-analyzer-dev — DynamoDB, S3 reports, Lambda env vars│ dev     │   1   │
│ CMK for img-analyzer-prod — DynamoDB, S3 reports, Lambda env var│ prod    │   1   │
│ img-analyzer-dev-phase2 — DynamoDB v2, SQS, S3 reports/SBOM     │ dev     │   2   │
│ img-analyzer-prod-phase2 — DynamoDB v2, SQS, S3 reports/SBOM    │ prod    │   2   │
│ img-analyzer-dev-phase3 — DynamoDB v3 and Secrets Manager       │ dev     │   3   │
│ img-analyzer-prod-phase3 — DynamoDB v3 and Secrets Manager      │ prod    │   3   │
└─────────────────────────────────────────────────────────────────┴─────────┴───────┘
```

### WAF WebACLs

```
┌──────────────────────────────────────┬─────────────┬─────────────────────────────────────────┐
│ Name                                 │ Scope       │ Rules                                   │
├──────────────────────────────────────┼─────────────┼─────────────────────────────────────────┤
│ img-analyzer-dev-cloudfront          │ CLOUDFRONT  │ CommonRuleSet, KnownBadInputs, RateLimit│
│ img-analyzer-prod-cloudfront         │ CLOUDFRONT  │ CommonRuleSet, KnownBadInputs, RateLimit│
└──────────────────────────────────────┴─────────────┴─────────────────────────────────────────┘
```

Three additional `CreatedByCloudFront-*` WebACLs in the account belong to other projects.

---

## Related Documents

- `InfrastructureCostAnalysis.md` — initial Phase 1 cost estimates
- `InfrastructureCostAnalysisPoC.md` — PoC vs production two-scenario comparison
- `InfrastructureCostPortfolio.md` — portfolio-specific cost analysis (pre-Phase 2/3)
- `Phase2ProdDebuggingV1.md` — production debugging log (CORS, type mismatches, ECR failures)
