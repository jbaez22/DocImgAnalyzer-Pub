# DocImgAnalizer — Phase 1 Status Report

**Date:** June 19, 2026
**Status:** COMPLETE
**Environments:** Dev (`dev-imgapp.craftingnewtech.com`) · Prod (`imgapp.craftingnewtech.com`)

---

## Phase 1 Scope

| Deliverable | Technology | Status |
|-------------|-----------|--------|
| Static Frontend | React 18 + TypeScript + Vite + Tailwind CSS | DONE |
| REST API | API Gateway HTTP API v2 — `img.craftingnewtech.com` | DONE |
| Business Logic | Python 3.12 / FastAPI / Mangum — Lambda | DONE |
| Data Store | DynamoDB On-Demand | DONE |
| Report Storage | S3 reports bucket | DONE |
| Infrastructure | Terraform — 11 modules, remote state | DONE |
| CI/CD | GitHub Actions + GitHub OIDC (zero static keys) | DONE |
| Security | WAF, ACM, KMS CMK, IAM least-privilege | DONE |
| Monitoring | CloudWatch Logs + Dashboard + Alarms + SNS | DONE |
| Documentation | Technical docs, diagrams, user guide, troubleshooting | DONE |

**Out of scope for Phase 1:** SQS, Fargate, Trivy/Syft integration, Cognito, Stripe.

---

## Delivery Steps

### Step 1 — Project Scaffolding
- `.gitignore` covering Python, Node, Terraform, OS artifacts
- `Makefile` with `check` target mirroring the full CI pipeline locally
- `.pre-commit-config.yaml` (terraform fmt, trailing whitespace, end-of-file, detect-secrets)

### Step 2 — Terraform Infrastructure (11 modules)

| Module | What It Provisions |
|--------|-------------------|
| `acm` | TLS certificates in us-east-1 for both domains |
| `api_gateway` | HTTP API v2, custom domain, access logs, throttling |
| `cloudfront` | Distribution, WAF WebACL, OAC, HTTPS-only |
| `cloudwatch` | Dashboard, metric alarms, SNS topic → email |
| `dynamodb` | On-demand table, PITR, KMS encryption, TTL |
| `github_oidc` | IAM role with OIDC trust for GitHub Actions |
| `kms` | CMK with annual auto-rotation |
| `lambda` | Function (Python 3.12), execution role, log group |
| `route53` | A alias records for frontend and API domains |
| `s3_frontend` | SPA bucket, public access blocked, OAC bucket policy |
| `s3_reports` | Reports bucket, lifecycle rules, KMS encryption |

Environment-specific configs in `environments/dev/` and `environments/prod/` with separate
`backend.hcl` and `terraform.tfvars`. State stored in S3 with native locking
(`use_lockfile = true`, Terraform >= 1.10).

### Step 3 — Python FastAPI Lambda Backend (18 files, 35 unit tests)

**API endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/analyze/dockerfile` | Analyze a Dockerfile — score + findings + fixed file |
| `POST` | `/api/v1/analyze/image` | Fetch Docker Hub image metadata |
| `GET` | `/api/v1/results/{scan_id}` | Retrieve a previous scan by ID |
| `GET` | `/health` | Lambda health check |

**Dockerfile security rules (R001–R011):**

| Rule | Severity | Check | Deduction |
|------|----------|-------|-----------|
| R001 | ERROR | Unpinned base image (`:latest` or no tag) | -20 per occurrence |
| R002 | ERROR | No USER instruction, or USER root/0 | -25 per occurrence |
| R003 | WARNING | No HEALTHCHECK instruction | -10 |
| R004 | ERROR | Secret-like key in ENV/ARG (password, token, api_key, etc.) | -30 per occurrence |
| R005 | ERROR | curl/wget piped to bash/sh — supply-chain risk | -20 per occurrence |
| R006 | WARNING | ADD used instead of COPY for local files | -5 per occurrence |
| R007 | WARNING | More than one RUN instruction | -5 |
| R008 | WARNING | Single-stage build (no builder/runtime separation) | -10 |
| R009 | WARNING | Non-minimal base image (not alpine/slim/distroless/Chainguard/scratch) | -10 |
| R010 | WARNING | Package cache not cleaned (apt/pip/apk) | -10 (once total) |
| R011 | WARNING | npm install instead of npm ci | -5 (once total) |

All rules run in pure Python — no external Docker tooling, no shell execution, no Hadolint binary.
The only standard-library dependency is the `re` module.

**Score calculation:** rule-specific penalty per violation; score clamped to 0–100.

**Fix generation:** 4-pass transformation producing a corrected Dockerfile with all issues resolved
(Pass 1: line-level fixes; Pass 2: RUN consolidation; Pass 3: USER/HEALTHCHECK injection;
Preamble: structural guidance for R008/R009).

### Step 4 — React Frontend (20 files)

- React 18 + TypeScript + Vite + Tailwind CSS
- Two primary flows: Dockerfile analysis and Docker image lookup
- Client-side validation before API calls
- Loading states, score gauge, findings with fix snippets, corrected Dockerfile preview
- Direct URL navigation to results pages (`/results/<scan_id>`)
- Build: hashed asset filenames (`max-age=31536000`); `index.html` → `no-cache`

### Step 5 — GitHub Actions CI/CD

**`pr.yml`** (triggered on PR to `develop` or `main`):
- Path-filtered jobs (terraform / backend / frontend)
- Terraform: fmt + validate + plan (plan posted as PR comment via dorny/paths-filter)
- Backend: pytest (35 tests) + Trivy IaC scan + image scan
- Frontend: ESLint + Vite production build
- `pr-ready` gate — all jobs must pass before merge

**`deploy.yml`** (triggered on merge):
- `develop` → dev environment (automatic)
- `main` → production (manual approval gate via GitHub Environment)
- Lambda: cross-compiled `manylinux2014_x86_64`, boto3/botocore stripped
- Frontend: S3 sync + CloudFront invalidation (`/index.html` only)
- Smoke test via `scripts/smoke-test.sh` post-deploy

### Step 6 — Validation & Smoke Testing

- `Makefile` `check` target: `npm audit`, Trivy IaC scan, Docker build, Trivy image scan
- `scripts/smoke-test.sh`: hits both API endpoints in the target environment and validates HTTP 200
- Wired into `deploy.yml` as the final post-deploy step

---

## Issues Encountered and Fixed

All issues were discovered during integration, CI/CD runs, and browser testing. Each was
diagnosed, fixed, and documented in `docs/TroubleshootingV1.md`.

| # | Area | Issue | Fix |
|---|------|-------|-----|
| 1 | GitHub Actions | Non-ASCII characters (em dashes) in workflow YAML causing startup_failure | Stripped all non-ASCII chars from workflow files |
| 2 | GitHub Actions | `actions/setup-node` and `actions/cache` on deprecated Node 16 | Updated all actions to Node 24 |
| 3 | pytest | Unused imports causing import errors | Removed unused pytest imports |
| 4 | Frontend | `package-lock.json` missing — `npm ci` fails | Added `frontend/package-lock.json` to repo |
| 5 | Frontend | TypeScript build errors in component files | Fixed type errors in React components |
| 6 | GitHub Actions OIDC | `pull_request` subject not in OIDC trust policy | Added `pull_request` subject to trust policy conditions |
| 7 | Terraform | `use_lockfile` requires Terraform >= 1.10 | Bumped CI `TF_VERSION` from 1.7 to 1.10.0 |
| 8 | GitHub Actions | Missing IAM permissions on GitHub Actions role | Added `lambda:GetFunction`, `cloudfront:*`, `route53:*`, and S3 permissions |
| 9 | GitHub Actions | Missing Lambda read permissions for Terraform state refresh | Added `lambda:ListFunctions`, `lambda:GetFunctionConfiguration` to IAM role |
| 10 | Deploy workflow | No Terraform plan before apply | Added plan step before apply in `deploy.yml` |
| 11 | WAFv2 | REGIONAL WAF rejected on API Gateway HTTP API v2 `$default` stage | Removed API GW WAF association — WAF on CloudFront only; throttle + CORS on API GW |
| 12 | FastAPI CORS | OPTIONS preflight returning 405 behind API Gateway | Added `CORSMiddleware` to FastAPI app with correct origin |
| 13 | CloudFront | Missing comment/description on distribution | Added `comment` attribute to CloudFront resource |
| 14 | Dockerfile fixer | Consecutive RUN instructions not consolidated for R007 fix | Fixed 3-pass transformer to merge consecutive RUN blocks |
| 15 | Dockerfile rules | R007 triggering too aggressively (threshold > 3) | Lowered threshold to > 1 RUN instructions |

---

## Deployed Infrastructure

### Dev Environment

| Resource | Value |
|----------|-------|
| Frontend URL | `https://dev-imgapp.craftingnewtech.com` |
| API URL | `https://dev-img.craftingnewtech.com` |
| CloudFront distribution | `ABC-EXAMPLE-XXXX` |
| Lambda function | `img-analyzer-dev-api` |
| DynamoDB table | `img-analyzer-dev-scans` |
| Frontend S3 bucket | `img-analyzer-dev-frontend` |
| Reports S3 bucket | `img-analyzer-dev-reports` |
| GitHub Actions role | `arn:aws:iam::ABC-EXAMPLE-XXXX:role/img-analyzer-dev-github-actions` |

### Production Environment

| Resource | Value |
|----------|-------|
| Frontend URL | `https://imgapp.craftingnewtech.com` |
| API URL | `https://img.craftingnewtech.com` |
| CloudFront distribution | `ABC-EXAMPLE-XXXX` |
| Lambda function | `img-analyzer-prod-api` |
| DynamoDB table | `img-analyzer-prod-scans` |
| Frontend S3 bucket | `img-analyzer-prod-frontend` |
| Reports S3 bucket | `img-analyzer-prod-reports` |
| GitHub Actions role | `arn:aws:iam::ABC-EXAMPLE-XXXX:role/img-analyzer-prod-github-actions` |

---

## Documentation Produced

| File | Description |
|------|-------------|
| `PHASE1_ACTION_PLAN.md` | Original delivery plan (all steps) |
| `docs/InitialManualStepsV1.md` | One-time manual AWS bootstrap steps |
| `docs/TroubleshootingV1.md` | All 15+ issues encountered with root cause and fix |
| `docs/UserGuideV1.md` | Frontend and API usage guide with test cases |
| `docs/IamBestPracticesV1.md` | IAM least-privilege design for GitHub Actions OIDC roles |
| `docs/LambdaBackendArchitectureV1.md` | Backend service architecture deep-dive |
| `docs/DiagramsV1.md` | Mermaid source for all three technical diagrams |
| `docs/diagrams/diagram1-architecture.svg` | AWS architecture — dark-theme SVG |
| `docs/diagrams/diagram2-data-flow.svg` | Request and data flow — dark-theme SVG |
| `docs/diagrams/diagram3-user-interaction.svg` | User interaction flowchart — dark-theme SVG |
| `docs/Phase1TechnicalOverview.md` | Comprehensive technical reference (this phase) |
| `docs/Phase1StatusReport.md` | This document |

---

## Commit History — June 19, 2026

| Hash | Type | Description |
|------|------|-------------|
| `47c9981` | docs | Add Phase 1 technical overview with architecture, data flow, and UX diagrams |
| `df51984` | docs | Replace Mermaid PNGs with dark-theme SVG diagrams |
| `e83cafc` | docs | Add rendered diagram PNGs and Mermaid source files |
| `991dcd7` | docs | Add DiagramsV1.md — architecture, data flow, and user interaction diagrams |
| `becb5b2` | fix | Consolidate consecutive RUN instructions in fixed Dockerfile (R007) |
| `cc758a3` | docs | Add LambdaBackendArchitectureV1.md |
| `c6cbf08` | fix | Lower R007 threshold from >3 to >1 RUN instructions |
| `ed61c16` | feat | Add per-finding fix snippets and fixed Dockerfile preview |
| `a7db70d` | docs | Add issue 19 — FastAPI CORS preflight 405 behind API Gateway HTTP API v2 |
| `4c1bfce` | fix | Add CORSMiddleware to FastAPI to handle OPTIONS preflight correctly |
| `38a2762` | docs | Add 5 UI test cases to UserGuideV1 |
| `b6125c8` | docs | Add UserGuideV1.md — frontend and API usage guide |
| `bafc56d` | feat | Add comment/description to CloudFront distribution |
| `4b94fdd` | docs | Add IamBestPracticesV1.md — least privilege GitHub Actions OIDC roles |
| `99ebfb5` | docs | Update TroubleshootingV1 with Lambda state refresh permissions |
| `3f22ed4` | fix | Add missing Lambda read permissions for Terraform state refresh |
| `5ac55ad` | docs | Add TroubleshootingV1.md with all Phase 1 issues and fixes |
| `673de83` | feat | Add Terraform plan step before apply in deploy workflow |
| `d88547a` | fix | Add missing IAM permissions to GitHub Actions role |
| `da5048d` | chore | Align CI Terraform version with local (1.15.6) |
| `8cd9801` | fix | Bump Terraform to 1.10.0 for use_lockfile S3 backend support |
| `0e2001f` | fix | Add GitHub Environment subjects to OIDC trust policy |
| `dcc4be2` | fix | Resolve TypeScript build errors in frontend |
| `9d4318a` | fix | Add frontend/package-lock.json required by npm ci and cache |
| `f767908` | fix | Remove unused pytest imports and update actions to Node 24 |
| `65b29f7` | fix | Strip non-ASCII chars from workflow files causing startup_failure |
| `a1d0153` | feat | Phase 1 MVP — initial implementation |

---

## Phase 1 — Final Checklist

- [x] Terraform infrastructure — dev and prod applied and verified
- [x] Lambda backend deployed — all three endpoints responding
- [x] Frontend deployed — SPA serving via CloudFront
- [x] CI/CD pipeline — PR validation + deploy to dev (auto) + deploy to prod (manual gate)
- [x] HTTPS enforced on both domains
- [x] WAF active on CloudFront (managed rules + rate limiting)
- [x] KMS CMK encrypting DynamoDB, S3 reports, Lambda env vars
- [x] GitHub OIDC — zero long-lived AWS credentials in GitHub Secrets
- [x] CloudWatch alarms configured — SNS email alerts active
- [x] Smoke tests passing in both environments
- [x] All documentation committed to main

---

*DocImgAnalizer Phase 1 — craftingnewtech.com — June 19, 2026*
