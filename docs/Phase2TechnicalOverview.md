# DocImgAnalizer — Phase 2 Technical Overview

**Phase 2** adds authenticated users, deep vulnerability scanning via Trivy + Syft, and
asynchronous processing — all without modifying Phase 1 infrastructure.

- **Frontend:** https://imgapp.craftingnewtech.com (Phase 1 URL, Phase 2 pages added)
- **API v1 (anonymous):** https://img.craftingnewtech.com/api/v1/ — unchanged
- **API v2 (authenticated):** https://img.craftingnewtech.com/api/v2/

---

## What Phase 2 Adds

| ----------------------- | ----------------------------------------------- | -------------------------------------------------------------- |
| Feature                 | Technology                                      | Notes                                                          |
| ----------------------- | ----------------------------------------------- | -------------------------------------------------------------- |
| **User authentication** | Amazon Cognito User Pool                        | Sign up, sign in, email verification, JWT                      |
| **API authorization**   | API Gateway JWT authorizer                      | Phase 1 routes open; Phase 2 routes require valid JWT          |
| **Deep image scan**     | Trivy CVE + Syft SBOM on ECS Fargate            | Full CVE report + CycloneDX SBOM; cannot run in Lambda         |
| **Async processing**    | SQS + EventBridge Pipes → Fargate               | POST returns `scan_id` immediately; frontend polls for results |
| **Scan history**        | DynamoDB v2 GSI on `user_id`                    | Per-user scan listing; authenticated scans stored without TTL  |
| **Container registry**  | Amazon ECR                                      | Scanner container image (Trivy + Syft)                         |
| **Private networking**  | VPC + private subnets + VPC Interface Endpoints | No NAT Gateway — cost-optimized                                |
| **API v2**              | FastAPI `/api/v2/` on Lambda v2                 | New routes requiring auth; v1 routes untouched                 |
| ----------------------- | ----------------------------------------------- | -------------------------------------------------------------- |

**Phase 1 is never modified.** The Phase 1 Lambda, DynamoDB table, S3 buckets, and API
routes continue operating independently throughout Phase 2 development and deployment.

---

## Architecture

```
                   ┌──────────────────────────────────────────────┐
                   │           Cognito User Pool                  │
                   │  Sign up · Sign in · Email verification      │
                   └──────────────────┬───────────────────────────┘
                                      │ JWT (RS256)
User (Browser)                        │
    │                                 ▼
    ├── HTTPS ──► imgapp.craftingnewtech.com (CloudFront → S3 — Phase 1, unchanged)
    │
    └── HTTPS ──► img.craftingnewtech.com (API Gateway — same gateway, Phase 1 domain)
                      │
                      ├── /api/v1/* ──► Lambda v1 (Phase 1 — anonymous, no auth)
                      │
                      └── /api/v2/* ──► JWT Authorizer (Cognito)
                                            │
                                            ▼
                                     Lambda v2 (FastAPI v2)
                                            │
                          ┌─────────────────┼───────────────────────┐
                          │                 │                       │
                          ▼                 ▼                       ▼
                       SQS Queue       DynamoDB v2             S3 Reports
                    (scan jobs)    (user scans + GSI)     (CVE JSON + SBOM)
                          │
                          ▼
               ┌──────── VPC ─────────────────────────────────────────────┐
               │                                                           │
               │  EventBridge Pipe: SQS → ECS Fargate (1 task/message)   │
               │                                                           │
               │  ┌──────────────────────────────────────────────────┐    │
               │  │  scan.py (Fargate task)                          │    │
               │  │  ├── trivy image <name>  → CVE JSON → S3         │    │
               │  │  └── syft <name>         → SBOM (CycloneDX) → S3 │    │
               │  │  └── update DynamoDB: status=COMPLETE            │    │
               │  └──────────────────────────────────────────────────┘    │
               │                                                           │
               │  VPC Interface Endpoints (no NAT Gateway):               │
               │  ECR API · ECR DKR · SQS · CloudWatch Logs              │
               │  Gateway Endpoints: S3 · DynamoDB (free)                │
               └───────────────────────────────────────────────────────────┘
```

---

## Async Scan Flow

```
1.  User POSTs /api/v2/analyze/image  (Authorization: Bearer <jwt>)
2.  API Gateway validates JWT via Cognito authorizer
3.  Lambda v2 creates scan_id (UUID), writes PENDING record to DynamoDB v2
4.  Lambda v2 sends { scan_id, image_name, user_id } to SQS
5.  Lambda v2 returns HTTP 202 { scan_id, status: "PENDING" }
6.  Frontend polls GET /api/v2/results/{scan_id} every 5 seconds
7.  EventBridge Pipe detects SQS message, launches Fargate task
8.  Fargate task:
      a. Runs `trivy image <name>` → CVE JSON
      b. Runs `syft <name> -o cyclonedx-json` → SBOM
      c. Uploads both reports to S3
      d. Updates DynamoDB: status=COMPLETE, cve counts, S3 keys
9.  Frontend receives COMPLETE → renders CVE table and SBOM download link
```

**Error path:** If Fargate task fails after 3 SQS receive attempts, the message moves to
the DLQ. A CloudWatch alarm fires, the SNS topic sends an email, and the scan record is
updated to `FAILED`.

---

## VPC Design

| ------------------- | ------------------------------------------------------ |
| Resource            | Value                                                  |
| ------------------- | ------------------------------------------------------ |
| VPC CIDR            | `10.0.0.0/16`                                          |
| Private subnets     | `10.0.1.0/24` (us-east-1a), `10.0.2.0/24` (us-east-1b) |
| Public subnets      | None — Fargate has no public IP                        |
| NAT Gateway         | None — replaced by VPC Interface Endpoints             |
| Interface Endpoints | ECR API, ECR DKR, SQS, CloudWatch Logs                 |
| Gateway Endpoints   | S3, DynamoDB (free)                                    |
| ------------------- | ------------------------------------------------------ |

No internet egress from Fargate tasks. All AWS API calls route privately through VPC
endpoints. The scanner pulls its image from ECR (not Docker Hub) via the ECR DKR endpoint.

---

## API v2 Endpoints

All `/api/v2/` routes require `Authorization: Bearer <access_token>` except `/health`.

| -------- | ---------------------------- | -------------------------------------- |
| Method   | Path                         | Description                            |
| -------- | ---------------------------- | -------------------------------------- |
| `GET`    | `/api/v2/health`             | Health check (no auth)                 |
| `POST`   | `/api/v2/analyze/dockerfile` | Authenticated Dockerfile analysis      |
| `POST`   | `/api/v2/analyze/image`      | Submit deep image scan (202 + scan_id) |
| `GET`    | `/api/v2/results/{scan_id}`  | Poll scan status and retrieve results  |
| `GET`    | `/api/v2/scans`              | List authenticated user's scan history |
| `DELETE` | `/api/v2/scans/{scan_id}`    | Delete a scan from history             |
| -------- | ---------------------------- | -------------------------------------- |

Phase 1 routes (`/api/v1/*`) remain unchanged and require no authentication.

---

## DynamoDB v2 Schema

**Table:** `img-analyzer-{env}-scans-v2`

| --------------- | ------ | --------------------------------------------- |
| Attribute       | Type   | Role                                          |
| --------------- | ------ | --------------------------------------------- |
| `scan_id`       | String | Partition Key                                 |
| `user_id`       | String | GSI PK (`user-scans-index`)                   |
| `created_at`    | String | ISO 8601 timestamp (GSI SK)                   |
| `scan_type`     | String | `dockerfile` or `image`                       |
| `status`        | String | `PENDING`, `PROCESSING`, `COMPLETE`, `FAILED` |
| `image_name`    | String | Docker image reference                        |
| `report_s3_key` | String | CVE report S3 key                             |
| `sbom_s3_key`   | String | SBOM S3 key                                   |
| `cve_critical`  | Number | Count of CRITICAL CVEs                        |
| `cve_high`      | Number | Count of HIGH CVEs                            |
| `ttl`           | Number | Epoch; null for authenticated scans           |
| --------------- | ------ | --------------------------------------------- |

**GSI `user-scans-index`:** PK = `user_id`, SK = `created_at` — efficient per-user history.

---

## Security Design

| ------------------ | ---------------------------------------------------------------------------- |
| Control            | Implementation                                                               |
| ------------------ | ---------------------------------------------------------------------------- |
| Authentication     | Cognito User Pool — email + password, email verification required            |
| Authorization      | API Gateway native JWT authorizer — validates token before Lambda is invoked |
| Password policy    | Min 12 chars, upper + lower + number + symbol                                |
| Token lifetimes    | Access: 60 min, Refresh: 30 days                                             |
| User isolation     | All DynamoDB queries scoped to `user_id` from JWT `sub` claim                |
| Network            | Fargate in private subnets, no public IP, no internet egress                 |
| IAM isolation      | Phase 2 roles have no access to Phase 1 DynamoDB table or S3 buckets         |
| Encryption         | Phase 2 KMS CMK (separate from Phase 1) for DynamoDB v2, SQS, S3 buckets     |
| Container scanning | ECR `scan_on_push = true`; CI Trivy scan rejects HIGH/CRITICAL unfixed CVEs  |
| ------------------ | ---------------------------------------------------------------------------- |

---

## Infrastructure as Code

Phase 2 Terraform lives in `terraform/phase2/` with a separate state key. The Phase 1
state is never modified — Phase 2 reads Phase 1 outputs via a read-only remote state
data source.

```
terraform/phase2/
├── modules/
│   ├── kms_phase2/     # Phase 2 CMK (separate from Phase 1)
│   ├── vpc/            # VPC, private subnets, VPC Interface Endpoints
│   ├── cognito/        # User Pool, App Client, hosted UI domain
│   ├── sqs/            # Scan queue + DLQ, KMS encrypted
│   ├── ecr/            # Scanner image repository
│   ├── dynamodb_v2/    # scans-v2 table + user-scans-index GSI
│   ├── s3_phase2/      # CVE reports bucket + SBOM bucket
│   ├── iam_phase2/     # Lambda v2 role, Fargate task/exec roles, GitHub Actions role
│   ├── ecs/            # Fargate cluster, task definition, EventBridge Pipe
│   ├── lambda_v2/      # Lambda v2 function, JWT authorizer, API Gateway routes
│   └── monitoring_phase2/ # CloudWatch dashboard + alarms
├── environments/
│   ├── dev/            # dev/backend.hcl + terraform.tfvars
│   └── prod/           # prod/backend.hcl + terraform.tfvars
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
└── backend.tf
```

**State keys:**
- Dev: `docker-img-analyzer/phase2/dev/terraform.tfstate`
- Prod: `docker-img-analyzer/phase2/prod/terraform.tfstate`

---

## CI/CD Pipeline

```
Pull Request → phase2   →  phase2-pr.yml
  ├── Detect changed paths (dorny/paths-filter)
  ├── Terraform: fmt + validate + plan (dev) → posted as PR comment
  ├── Backend v2: ruff + mypy + pytest
  ├── Scanner: docker build + Trivy image scan (no HIGH/CRITICAL unfixed)
  ├── Frontend: ESLint + Vite build
  └── pr-ready gate (all jobs must pass)

Merge → phase2          →  phase2-deploy.yml  →  dev (automatic)
workflow_dispatch       →  phase2-deploy.yml  →  prod (manual approval: phase2-production)
```

**Phase 1 pipelines (`pr.yml`, `deploy.yml`) are not modified.** They continue to deploy
Phase 1 independently on `main` / `develop` branch changes.

---

## Estimated AWS Cost (Phase 2 add-on)

| ----------------------- | ----------------- | ----------------------------------- |
| Service                 | Est. / month      | Notes                               |
| ----------------------- | ----------------- | ----------------------------------- |
| Cognito                 | ~$0               | Free for first 50,000 MAU           |
| SQS                     | ~$0               | 1M requests/month free tier         |
| ECR                     | ~$1               | Scanner image ~500 MB               |
| VPC Interface Endpoints | ~$29              | 4 endpoints × $0.01/hr × 720 hr     |
| ECS Fargate             | ~$5–20            | ~$0.003/scan; varies by volume      |
| DynamoDB v2             | ~$1               | On-Demand, low scan volume          |
| S3 (CVE/SBOM)           | ~$1               | Sub-GB initially                    |
| CloudWatch              | ~$2               | Fargate logs + Phase 2 dashboard    |
| KMS Phase 2             | ~$1               | $1/CMK/month                        |
| **Total add-on**        | **~$40–55/month** | VPC endpoints are the dominant cost |
| ----------------------- | ----------------- | ----------------------------------- |

---

