# DocImgAnalizer — Phase 2 Status Report

**Date:** 2026-07-07  
**Status:** COMPLETE — merged to `develop` at `94f37d4`  
**Branch:** `phase2` → merged to `develop`  
**Environments:** Dev (`dev-imgapp.craftingnewtech.com`) · Prod (`imgapp.craftingnewtech.com`)

---

## Phase 2 Scope

| Deliverable | Technology | Status |
|-------------|-----------|--------|
| User authentication | Amazon Cognito User Pool | COMPLETE |
| API authorization | API Gateway JWT authorizer + Cognito | COMPLETE |
| Async scan processing | Amazon SQS + EventBridge Pipes | COMPLETE |
| Deep vulnerability scanning | Trivy + Syft on ECS Fargate | COMPLETE |
| Container image registry | Amazon ECR (immutable tags, lifecycle policy) | COMPLETE |
| VPC + private networking | VPC + Interface Endpoints (no NAT) | COMPLETE |
| API v2 | FastAPI `/api/v2/` on Lambda | COMPLETE |
| User scan history | DynamoDB v2 + GSI on `user_id` | COMPLETE |
| Frontend auth + new pages | React + AWS Amplify Auth | DEFERRED TO PHASE 3 |
| Infrastructure | Terraform `terraform/phase2/` (11 modules) | COMPLETE |
| CI/CD | `phase2-pr.yml` + `phase2-deploy.yml` | COMPLETE |
| Documentation | Technical overview, user guide, backend arch | COMPLETE |

**Out of Scope for Phase 2:** Stripe billing, API keys for CI/CD, GitHub Action marketplace
listing, organizational accounts, EventBridge re-scanning.

---

## Phase 1 Uptime Guarantee

Phase 1 Lambda (`img-analyzer-{env}-api`) remains live and serving `/api/v1/*` throughout
Phase 2 development. The only Phase 1 file touched in Phase 2: OIDC trust policy in
`terraform/phase1/modules/iam/main.tf` — one additive condition added (`refs/heads/phase2`).

---

## Implementation Steps

### Step 0 — Repository Restructuring
- [x] `terraform/` moved to `terraform/phase1/` — state keys unchanged
- [x] `pr.yml`, `deploy.yml`, `Makefile` path filters updated to `terraform/phase1/**`
- [x] `backend/app/main.py` frozen with header comment
- [x] `phase2` branch created from `main`

### Step 1 — VPC + Networking
- [x] Scaffold: `terraform/phase2/modules/vpc/` with VPC, private subnets, Interface Endpoints
- [x] Terraform plan review
- [x] `terraform apply` in dev
- [x] Verify endpoints connectivity from Fargate task — scanner completed without NAT; all S3/DDB/ECR traffic through VPC endpoints

### Step 2 — Cognito
- [x] Scaffold: `terraform/phase2/modules/cognito/` with User Pool + App Client + domain
- [x] Terraform plan review
- [x] `terraform apply` in dev
- [x] End-to-end: sign up → email verification → sign in (test user `e2e-test@example.com`)
- [x] Verify JWT authorizer rejects unauthenticated requests — 401 confirmed in test suite and live API

### Step 3 — KMS Phase 2 + SQS + DynamoDB v2
- [x] Scaffold: `terraform/phase2/modules/kms_phase2/`
- [x] Scaffold: `terraform/phase2/modules/sqs/` — scan queue + DLQ
- [x] Scaffold: `terraform/phase2/modules/dynamodb_v2/` — table + GSI + PITR + TTL
- [x] Terraform plan review
- [x] `terraform apply` in dev
- [x] Verify KMS encryption on all resources — KMS CMK confirmed on DynamoDB, SQS, S3 phase2 buckets

### Step 4 — ECR + Scanner Container
- [x] Scaffold: `terraform/phase2/modules/ecr/`
- [x] Scaffold: `backend/scanner/Dockerfile` — Trivy + Syft multi-stage
- [x] Scaffold: `backend/scanner/scan.py` — SQS message → Trivy + Syft → S3 + DDB
- [x] `docker build` + local test with sample image — fixed binary paths; pinned `aquasec/trivy:0.72.0` + `anchore/syft:v1.46.0`
- [x] Trivy scan of built scanner image — 3 upstream gobinary CVEs triaged in `.trivyignore`; OS + Python layers clean
- [x] Push to ECR via CI — scanner image `v8` at task def revision 16

### Step 5 — ECS Fargate
- [x] Scaffold: `terraform/phase2/modules/ecs/` — cluster + task + EventBridge Pipe
- [x] Terraform plan review
- [x] `terraform apply` in dev
- [x] Verify Fargate task completes in private subnet — E2E smoke test confirmed PENDING → PROCESSING → COMPLETE
- [x] Verify no public IP assigned to task — `assign_public_ip = "DISABLED"` enforced in EventBridge Pipe config
- [ ] Test DLQ: verify failed scan → DLQ → alarm fires *(deferred — alarms are deployed; explicit DLQ trigger test not run)*

### Step 6 — Lambda v2 + API Gateway JWT Authorizer
- [x] Scaffold: `backend/v2/` — FastAPI v2, routers, services, auth, models, db
- [x] Scaffold: `terraform/phase2/modules/lambda_v2/` — JWT authorizer + routes
- [x] Implement `auth/cognito.py` — JWKS fetch + RS256 decode
- [x] Implement `db/dynamodb.py` — all DDB v2 access patterns
- [x] Implement `services/sqs_producer.py` — SQS enqueue
- [x] Implement routers: `analyze.py`, `results.py`, `scans.py`
- [x] Unit tests — 76 tests passing (22 v2 router tests + 37 rule engine + 17 v1)
- [x] Terraform plan review + apply
- [x] Verify JWT authorizer returns 401 for unauthenticated requests — confirmed live
- [x] Verify `/api/v1/` routes unaffected — Phase 1 Dockerfile analysis still works anonymously

### Step 7 — Frontend Auth + New Pages
- [ ] Install `@aws-amplify/auth` *(DEFERRED TO PHASE 3)*
- [ ] `AuthContext.tsx` + `ProtectedRoute.tsx` *(DEFERRED TO PHASE 3)*
- [ ] Sign in / sign up pages *(DEFERRED TO PHASE 3)*
- [ ] Dashboard (scan history) *(DEFERRED TO PHASE 3)*
- [ ] Deep scan results page *(DEFERRED TO PHASE 3)*
- [ ] Status polling component *(DEFERRED TO PHASE 3)*

### Step 8 — Monitoring Phase 2
- [x] Scaffold: `terraform/phase2/modules/monitoring_phase2/` — dashboard + alarms
- [x] Terraform apply
- [ ] Verify SQS DLQ alarm fires on test message *(deferred with Step 5 DLQ test)*
- [ ] Verify Lambda v2 error alarm fires on test error *(deferred)*

### Step 9 — CI/CD Phase 2
- [x] `phase2-pr.yml` — path-filtered to `terraform/phase2/**`, `backend/v2/**`, `backend/scanner/**`
- [x] `phase2-deploy.yml` — dev (auto on push), prod (manual approval)
- [x] GitHub Environments: `phase2-development` (auto) and `phase2-production` (manual approval)
- [x] `AWS_ROLE_ARN` variable set at environment level
- [x] First pipeline run end-to-end — green as of 2026-07-07

### Step 10 — Validation + Definition of Done
- [x] Sign up → sign in → submit image scan → poll status → view CVE results — E2E smoke test passed
- [x] Authenticated Dockerfile analysis — `/api/v2/analyze/dockerfile` confirmed
- [x] Phase 1 anonymous flows still work — `/api/v1/analyze` unaffected
- [ ] SQS DLQ test: failed scan → DLQ → alarm fires *(deferred)*
- [ ] IAM: Phase 2 role cannot access Phase 1 DynamoDB or S3 *(policy simulator check deferred — scoped by ARN prefix in policy)*
- [x] JWT: missing token → 401 confirmed live; test suite covers auth edge cases
- [x] All Phase 2 data encrypted with Phase 2 KMS CMK
- [x] No HIGH/CRITICAL unfixed CVEs in Lambda v2 deps or scanner image

---

## Definition of Done

- [x] Cognito User Pool deployed — sign up, email verification, sign in working
- [x] API Gateway JWT authorizer rejecting unauthenticated requests to `/api/v2/*`
- [x] `/api/v1/*` routes unaffected — Phase 1 still serves anonymous users
- [x] SQS queue + DLQ deployed and KMS encrypted
- [x] ECR repository with scanner image — 3 upstream CVEs triaged, OS/Python layers clean
- [x] Fargate task runs in private subnets — no public IP assigned
- [x] Trivy CVE scan completing and writing results to S3 + DynamoDB
- [x] Syft SBOM generation writing CycloneDX JSON to S3
- [ ] Frontend sign in/up flow *(deferred to Phase 3)*
- [ ] Frontend deep scan results page *(deferred to Phase 3)*
- [x] Phase 2 CI/CD pipeline passing
- [ ] Phase 2 GitHub Actions role isolation verified via policy simulator *(deferred)*
- [x] CloudWatch alarms deployed for SQS DLQ, Fargate failures, Lambda v2 errors
- [x] All Phase 2 data encrypted with Phase 2 KMS CMK
- [x] No HIGH/CRITICAL unfixed CVEs in Lambda v2 deps or scanner image

---

## Deferred Items (Phase 3 or Post-Launch)

| Item | Reason Deferred |
|------|----------------|
| Frontend auth + UI pages | Phase 3 scope — API-first approach; CLI/Postman usable now |
| SQS DLQ explicit trigger test | Alarms deployed; manual test can be done in Phase 3 |
| IAM Phase 2 role isolation simulator check | ARN-scoped policies provide isolation; formal check deferred |
| IAM `TerraformManageS3Phase2` lock-down | Access Analyzer collecting data until 2026-07-12; see `IAMAccessAnalyzerGuide.md` |

---

*DocImgAnalizer Phase 2 — craftingnewtech.com*
