# DocImgAnalizer — Live Architecture & Data Flow (2026-07-17)

Snapshot of prod's **actual live configuration**, captured directly from AWS (not from
Terraform source alone — see the Issues section for where the two disagree). Reflects the
Remediation panel and CVE Report/SBOM download fixes shipped 2026-07-16/17, plus the
NAT Gateway removal from the cost-reduction pass.

## Figure 1 — Edge & Request Routing

```
                                                    ┌──────────────┐
                                                    │ User Browser │
                                                    └──────────────┘
                                                           │
                       ┌───────────────────────────────────┴────────────────────────────────────┐
  ┌──────────────────────────────────────────┐                                     ┌─────────────────────────┐
  │ CloudFront                               │                                     │ API Gateway HTTP v2     │
  │ WebACL: img-analyzer-prod-cloudfront (!) │                                     │ Cognito JWT Authorizer  │
  │ imgapp.craftingnewtech.com               │                                     │ img.craftingnewtech.com │
  └──────────────────────────────────────────┘                                     └─────────────────────────┘
                       │                                                                        │
           ┌────────────────────────┐                       ┌──────────────────────────────────┬┴───────────────────────────────────┐
           │ S3 Frontend Bucket     │         ┌───────────────────────────┐       ┌──────────────────────────┐          ┌───────────────────────┐
           │ OAC — no public access │         │ Lambda v1 (Phase 1)       │       │ Lambda v2 (Phase 2)      │          │ Lambda v3 (Phase 3)   │
           └────────────────────────┘         │ Dockerfile Rules — FROZEN │       │ CVE Scan API + R012/R013 │          │ Billing / Keys / Orgs │
                                              │ /api/v1/*                 │       │ /api/v2/*                │          │ /api/v3/*             │
                                              └───────────────────────────┘       └──────────────────────────┘          └───────────────────────┘
                                                            │                                  │                                    │
                                                   ┌──────────────────┐            ┌───────────────────────┐            ┌────────────────────────┐
                                                   │ DynamoDB v1      │            │ DynamoDB v2 (SSE-S3)  │            │ DynamoDB v3 (3 tables) │
                                                   │ KMS CMK (phase1) │            │ + Async Scan Pipeline │            │ Secrets Mgr (Stripe)   │
                                                   └──────────────────┘            │ — see Fig. 2 —        │            │ KMS CMK (phase3)       │
                                                                                   └───────────────────────┘            └────────────────────────┘
```

**(!)** — the WAF WebACL shown on CloudFront is live right now but **should not be** — see
Issue 1 below. It was intentionally removed 2026-07-16 for cost savings and got resurrected
by an unrelated push. This diagram shows ground truth, not intent.

## Figure 1b — CloudFront + WAF Edge Detail

Figure 1 shows WAF only as an inline label on the CloudFront box. This is the same edge path
expanded to show exactly where WAF sits in the request chain and what it's currently
configured to do (pulled live via `aws wafv2 get-web-acl`).

```
                                     ┌──────────────┐
                                     │ User Browser │
                                     └──────────────┘
                                            │
                         ┌─────────────────────────────────────┐
                         │ Route53: imgapp.craftingnewtech.com │
                         │ A-alias -> CloudFront               │
                         └─────────────────────────────────────┘
                                            │
                        ┌───────────────────────────────────────┐
                        │ CloudFront Distribution ABC-EXAMPLE-XXXX │
                        │ Origin: S3 frontend bucket (OAC)      │
                        └───────────────────────────────────────┘
                                            │
                 ┌─────────────────────────────────────────────────────┐
                 │ WAFv2 WebACL: img-analyzer-prod-cloudfront (!)      │
                 │ Scope: CLOUDFRONT  |  Default action: Allow         │
                 │ Managed rules: AWSManagedRulesCommonRuleSet,        │
                 │                AWSManagedRulesKnownBadInputsRuleSet │
                 │ Custom rule:   RateLimitPerIP (1000 req / 5 min)    │
                 └─────────────────────────────────────────────────────┘
                                            │
                     ┌──────────────────────────────────────────────┐
                     │ S3 Frontend Bucket                           │
                     │ img-analyzer-prod-frontend (OAC-only access) │
                     └──────────────────────────────────────────────┘
```

**(!)** unintended — see Issue 1. Recreated by a stale `terraform apply` on 2026-07-16;
should have been destroyed permanently that day per the cost-reduction plan. Rules and rate
limit confirmed live via `aws wafv2 get-web-acl` — this is exactly what it would be doing if
it *were* intentional, not a placeholder guess.

**NAT Gateway cost, for reference:** AWS charges $0.045/hour + $0.045/GB data processed
(us-east-1) — ~$32.85/month per gateway on the hourly charge alone, before data-processing
fees. `docs/InfrastructureCostJul2026.md` recorded ~$32/month for NAT Gateway when it was
briefly evaluated for dev+prod; that number is what drove the decision to replace it with the
public-subnet Fargate + free VPC Gateway Endpoints design in Figure 2, which costs $0 and is
why it doesn't appear in any of these diagrams.

## Figure 2 — CVE Image Scan: Async Data Flow (latest changes)

This is where the NAT Gateway removal and the two frontend fixes from 2026-07-16/17 (Remediation
panel, blob-fetch download) actually live.

```
                                                 ┌────────────────────────────────────────┐
                                                 │ Lambda v2 — POST /api/v2/analyze/image │
                                                 └────────────────────────────────────────┘
                                                                     │
                                                    ┌──────────────────────────────────┐
                                                    │ SQS: img-analyzer-prod-scan-jobs │
                                                    │ SQS-managed SSE (no CMK)         │
                                                    └──────────────────────────────────┘
                                                                     │
                                                     ┌────────────────────────────────┐
                                                     │ EventBridge Pipe: scan-trigger │
                                                     │ 1 msg -> 1 Fargate RunTask     │
                                                     └────────────────────────────────┘
                                                                     │
                                              ┌──────────────────────────────────────────────┐
                                              │ ECS Fargate task (Trivy + Syft)              │
                                              │ Public subnet + assign_public_ip=ENABLED     │
                                              │ Internet Gateway direct -- NO NAT Gateway    │
                                              │ S3 + DynamoDB via free Gateway VPC Endpoints │
                                              └──────────────────────────────────────────────┘
                                                                     │
                             ┌───────────────────────────────────────┴──────────────────────────────────────────┐
           ┌────────────────────────────────────┐  ┌────────────────────────────────────┐      ┌─────────────────────────────────┐
           │ S3: cve-reports bucket             │  │ S3: sbom-reports bucket            │      │ DynamoDB v2: scans-v2           │
           │ SSE-S3 + CORS (GET, imgapp origin) │  │ SSE-S3 + CORS (GET, imgapp origin) │      │ status/cve_counts (SSE default) │
           └────────────────────────────────────┘  └────────────────────────────────────┘      └─────────────────────────────────┘


  ── Browser read / render / download path ──────────────────────────────────────────────────────────────────────────────────────────

                                                   ┌────────────────────────────────────┐
                                                   │ User Browser — DeepResultsPage.tsx │
                                                   └────────────────────────────────────┘
                                                                     │
                             ┌───────────────────────────────────────┴─────────────────────────────────────────┐
           ┌────────────────────────────────────┐                                         ┌──────────────────────────────────────────┐
           │ Poll GET /api/v2/results/{scan_id} │                                         │ CveFindings.tsx renders findings         │
           │ every 5s while PENDING/PROCESSING  │                                         │ + Remediation panel:                     │
           │ Lambda v2 reads DynamoDB v2,       │                                         │ Package Upgrades + Base Image suggestion │
           │ returns presigned report/sbom URLs │                                         └──────────────────────────────────────────┘
           └────────────────────────────────────┘
                             │
          ┌──────────────────────────────────────┐
          │ Download button -> fetch(url) + blob │
          │ GET direct to S3 (CORS preflight OK) │
          │ same-origin blob:// URL, forces save │
          └──────────────────────────────────────┘
```

**Confirmed via live AWS checks (not assumed from Terraform):**
- `aws ec2 describe-nat-gateways` on `vpc-ABC-EXAMPLE-XXXX` → empty. No NAT Gateway exists.
- VPC has only two Gateway endpoints (S3, DynamoDB) — no Interface endpoint for CloudWatch
  Logs was found live, despite `terraform/phase2/modules/vpc/main.tf` defining one; not
  investigated further today, flagged in Issue 4.
- `aws s3api get-bucket-cors` on both `img-analyzer-prod-cve-reports` and
  `img-analyzer-prod-sbom-reports` → CORS rule present, `GET` from
  `https://imgapp.craftingnewtech.com`, confirming the download fix's dependency is live.

---

## Issues found and solutions

### Issue 1 — WAF was resurrected on prod (live now, unintended)

**What happened:** `main`'s `terraform/phase1/main.tf` still declares `module "waf"` — the
WAF removal (2026-07-16, ~$8/month savings) was only ever committed on the `phase2` branch,
never merged to `main`. `main`'s `deploy.yml` runs `terraform apply -chdir=terraform/phase1`
on **every** push to `main` (unlike `phase2-deploy.yml`, which needs manual dispatch). My two
pushes to `main` yesterday (Remediation panel commit, download-blob-fix commit) each
auto-triggered that apply, and the first one recreated the WAF WebACL and re-associated it
with CloudFront.

**Confirmed via CloudTrail:** `CreateWebACL` called by `GitHubActions-Deploy-prod-29552649004`
at 2026-07-16T23:34:19-04:00 — exactly matching the CloudFront distribution's
`LastModifiedTime`. Not a guess; directly observed in the event log.

**Impact:** ~$8/month cost regression, live right now. No functional/security impact (WAF
being present isn't harmful, just not what was decided).

**Solution:** Port the WAF-removal diff from `phase2` to `main`'s
`terraform/phase1/main.tf` (remove `module "waf"` + the `waf_arn` wiring into
`module "cloudfront"`), then destroy the resurrected WebACL properly — CloudFront must be
updated to drop `WebACLId` **first** and confirmed `Deployed`, then the WAF WebACL destroyed
second (the known `WAFAssociatedItemException` ordering issue seen earlier this project). Do
this via a manual, sequenced local apply rather than letting the next `main` push's
single-shot `terraform apply -auto-approve` handle the ordering, since that pipeline has no
built-in sequencing for this dependency. Not yet done — pending your go-ahead.

### Issue 2 — API Gateway CORS regression: `DELETE` (and any future non-GET/POST) blocked

**What happened:** Same root cause as Issue 1. `main`'s
`terraform/phase1/modules/api_gateway/main.tf` still has
`allow_methods = ["GET", "POST", "OPTIONS"]`. `phase2-deploy.yml`'s prod job has a
`Patch API Gateway CORS (prod)` step that imperatively widens this via `aws apigatewayv2
update-api` to include `PUT, DELETE` — but that's a CLI patch, not Terraform-managed, so it's
silently undone every time `main`'s `terraform apply` for `terraform/phase1` runs (it resets
the API's CORS config back to its own narrower declaration).

**Confirmed live:** `aws apigatewayv2 get-api ... --query 'CorsConfiguration.AllowMethods'`
currently returns `POST, OPTIONS, GET` only — no `PUT`/`DELETE`. Phase 3 has a real route,
`DELETE /api/v3/keys/{key_id}` (API key deletion, used by `ApiKeysPage.tsx`), that requires a
`DELETE` CORS preflight to succeed. **This is currently broken for browser users right now** —
deleting an API key from the UI will fail with a CORS error.

**Solution:** Two parts —
1. Update `main`'s `terraform/phase1/modules/api_gateway/main.tf` `cors_configuration` to
   include `PUT`, `DELETE` (matching `phase2` branch), making it durable via Terraform.
2. Once durable, the imperative CLI patch step in `phase2-deploy.yml` becomes redundant and
   can be removed — it exists only as a workaround for `main`'s Terraform being wrong; fixing
   the source removes the need for the patch.

Not yet done — same batch as Issue 1's fix, since both are the same underlying file/pipeline.

### Issue 3 — `main` branch's `terraform/phase1` is a stale/diverging source of truth

**Root cause of both Issues 1 and 2.** All infra evolution this project (WAF removal, KMS
removal for Phase 2, CORS widening, dev decommission) happened on the `phase2` branch and was
applied via manual/`workflow_dispatch` runs **against `phase2`**, never merged back to `main`.
But `main`'s `deploy.yml` *also* owns and auto-applies `terraform/phase1` on every push —
nobody had been treating `main`'s Terraform as something that needed to stay in sync, since
day-to-day work happens on `phase2`.

**Solution (process, not just code):** Two real options, worth discussing rather than picking
for you:
- **(a)** Reconcile once now (merge `phase2` → `main` for `terraform/phase1` specifically,
  landing Issues 1+2's fixes as part of that), then establish a habit of diffing
  `terraform/phase1` between the two branches before any `main` push that touches
  infra-adjacent files.
- **(b)** Stop letting `main`'s `deploy.yml` auto-`terraform apply` on every push — require
  `workflow_dispatch` for the Terraform step specifically (keep frontend/Lambda-code deploys
  on auto-push, matching how `phase2-deploy.yml` already requires explicit dispatch for its
  own applies). This directly prevents a repeat of Issues 1/2 regardless of branch drift,
  at the cost of one extra manual step per infra-relevant `main` push.

### Issue 4 — CloudWatch Logs VPC Interface Endpoint declared but not found live

`terraform/phase2/modules/vpc/main.tf` defines `aws_vpc_endpoint.cloudwatch_logs` (Interface
type, ~$7/month, added specifically to fix `TaskFailedToStart` reliability from the public
subnet). Live check (`aws ec2 describe-vpc-endpoints`) shows only the two free Gateway
endpoints (S3, DynamoDB) — no Interface endpoint present. Not yet root-caused today; could be
another Terraform/actual-state drift, or the endpoint may have been intentionally removed
during the cost-cutting pass and the module file just wasn't updated to match. **Needs a
follow-up `terraform plan` against `phase2`'s own state** (not `main`'s, given Issue 3) to see
whether Terraform itself is aware of the gap, before doing anything.

---

## Summary — what needs your decision

|--------------------------------------------------------|-----------------------------------------------------|---------------------------------|-------------|
| Issue                                                  | Severity                                            | Fix effort                      | Status      |
|--------------------------------------------------------|-----------------------------------------------------|---------------------------------|-------------|
| 1. WAF resurrected on prod                             | Cost (~$8/mo), not urgent                           | Small, needs sequenced apply    | Not started |
| 2. API Gateway CORS missing PUT/DELETE                 | User-facing bug right now (API key deletion broken) | Small                           | Not started |
| 3. `main`'s terraform/phase1 drift (root cause of 1+2) | Process risk -- will recur                          | Needs a decision (a or b above) | Not started |
| 4. CloudWatch Logs VPC endpoint mismatch               | Unknown -- not yet root-caused                      | Investigation first             | Not started |
|--------------------------------------------------------|-----------------------------------------------------|---------------------------------|-------------|

Recommend prioritizing **Issue 2** first since it's an active user-facing bug (not just cost
or hygiene), likely bundled with Issue 1's fix since both are the same file/pipeline. Issue 3
needs your call on (a) vs (b). Issue 4 needs a quick investigation pass before any fix.
