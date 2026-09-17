# DocImgAnalizer — Phase 1 Technical Overview

**DocImgAnalizer** is a serverless SaaS tool that helps developers analyze Docker images and
Dockerfiles for security issues and best-practice violations — directly in the browser, with no
credentials or local tooling required.

- **Frontend:** https://imgapp.craftingnewtech.com
- **API:** https://img.craftingnewtech.com

---

## What Users Can Do

| Feature | How It Works |
|---------|-------------|
| **Dockerfile analysis** | Paste any Dockerfile and receive a security score (0–100), categorized findings with fix snippets, and a corrected Dockerfile |
| **Docker image lookup** | Enter any Docker Hub image name (e.g., `nginx:1.25-alpine`) and retrieve metadata: digest, architecture, OS, compressed size, and layer count |
| **Results retrieval** | Every scan gets a permanent scan ID — share or bookmark the URL to reload results at any time (stored 90 days) |

---

## Architecture

![AWS Architecture — DocImgAnalizer Phase 1](./diagrams/diagram1-architecture.svg)

The system is fully serverless. There are no EC2 instances, no container clusters, and no
idle compute costs.

| Component | Technology | Role |
|-----------|-----------|------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS | Single-page application |
| CDN | CloudFront + WAF WebACL | HTTPS termination, caching, managed WAF rules |
| DNS | Route 53 | A alias records for both domains |
| API | API Gateway HTTP API v2 | Throttling (burst 100 / rate 50 rps), CORS, routing |
| Backend | Lambda — Python 3.12 / FastAPI / Mangum | All business logic; 512 MB, 30 s timeout |
| Persistence | DynamoDB On-Demand + S3 | Scan records (90-day TTL) + full JSON reports |
| Security | KMS CMK + GitHub OIDC | Encryption at rest; zero long-lived AWS credentials |
| Observability | CloudWatch Logs / Dashboard / Alarms + SNS | Structured logs, metrics, email alerts |

---

## Data Flow

![Request and Data Flow](./diagrams/diagram2-data-flow.svg)

### Flow A — Dockerfile Analysis

1. The user pastes Dockerfile content into the form and clicks **Analyze**.
2. The React SPA POSTs `{ "content": "FROM ..." }` to `POST /api/v1/analyze/dockerfile` via
   API Gateway.
3. Lambda validates the request with Pydantic, then calls the **Dockerfile Analyzer** service.
4. The analyzer:
   - Parses all instructions (handling multi-line continuations and comments)
   - Runs eleven security rules (R001–R011) using regex and string matching
   - Calculates a weighted score from 0 to 100
   - Generates a corrected Dockerfile via a 3-pass transformation
5. Lambda writes the full report to S3 and a summary item to DynamoDB (TTL = 90 days).
6. The frontend renders the score gauge, findings with fix snippets, the corrected Dockerfile,
   and metadata.

### Flow B — Image Analysis

1. The user enters an image name (e.g., `nginx:1.25-alpine`) and clicks **Analyze**.
2. Lambda parses the image reference and calls the **Docker Hub REST API** — metadata only,
   no image is pulled.
3. The response includes: digest, architecture, OS, compressed size, and layer count.
4. Error handling is explicit:
   - Docker Hub 404 → `404 Not Found` with "image not found" message
   - Docker Hub 5xx / timeout → `502 Bad Gateway` with upstream error message

### Flow C — Results Retrieval

Any previous scan can be fetched via `GET /api/v1/results/<scan_id>`. Results pages support
direct URL navigation and browser refresh — the frontend re-fetches from the API on load.

---

## User Experience

![User Interaction Flow](./diagrams/diagram3-user-interaction.svg)

The application has two primary workflows, both following the same UX pattern:

1. **Input form** with inline validation (no API call for empty input)
2. **Loading state** with a status message while the API processes the request
3. **Results page** with structured output and a back-to-home link

**Dockerfile results include:**
- Score gauge (0–100) with error / warning / info counts
- Finding cards: rule ID, severity, description, and fix snippet
- Fixed Dockerfile rendered with syntax highlighting
- Metadata: instruction count, stage count, has HEALTHCHECK, has non-root USER

**Image results include:**
- Layer count badge
- Full image reference and digest (`sha256:...`)
- Architecture, OS, compressed size (bytes), tag status, last pushed date

---

## Dockerfile Security Rules

Phase 1 implements 11 rules covering the most impactful security and best-practice issues.

| Rule | Severity | What It Checks | Score Deduction |
|------|----------|---------------|----------------|
| R001 | ERROR | Base image uses `:latest` or has no tag | -20 per occurrence |
| R002 | ERROR | No `USER` instruction, or `USER root` / `USER 0` | -25 per occurrence |
| R003 | WARNING | No `HEALTHCHECK` instruction | -10 |
| R004 | ERROR | Secret-like key name in `ENV` or `ARG` (password, token, api_key, etc.) | -30 per occurrence |
| R005 | ERROR | `curl`/`wget` piped to `bash`/`sh` — supply-chain risk | -20 per occurrence |
| R006 | WARNING | `ADD` used for local files — prefer `COPY` | -5 per occurrence |
| R007 | WARNING | More than one `RUN` instruction — chain with `&&` to reduce layers | -5 |
| R008 | WARNING | Single-stage build — no builder/runtime stage separation | -10 |
| R009 | WARNING | Final base image is not a minimal variant (not alpine, slim, distroless, Chainguard, or scratch) | -10 |
| R010 | WARNING | Package cache not cleaned: `apt-get` without `rm -rf /var/lib/apt/lists/*`, `pip` without `--no-cache-dir`, `apk` without `--no-cache` | -10 (once total) |
| R011 | WARNING | `npm install` instead of `npm ci` — not lock-file-enforced | -5 (once total) |

**Scoring:** violations deduct points per rule as shown above. Score is clamped to 0–100.
A score of 100 means zero violations.

---

## Security Design

| Control | Implementation |
|---------|---------------|
| Transport | HTTPS only, TLS 1.2+; CloudFront enforces redirect HTTP → HTTPS |
| WAF | Managed AWS rule groups + rate limit 1,000 req / 5 min on CloudFront |
| API throttling | Burst 100 / rate 50 rps on API Gateway |
| CORS | Only `https://imgapp.craftingnewtech.com` — no wildcard, no localhost in production |
| Encryption at rest | KMS CMK (auto-rotate annually) covering DynamoDB, S3 reports bucket, Lambda env vars |
| S3 frontend | Public access blocked; served exclusively via CloudFront OAC |
| CI/CD credentials | GitHub OIDC — no long-lived AWS access keys stored anywhere |
| Docker Hub calls | REST API for metadata only — no image pull, no Docker daemon, no credentials |

---

## Observability

- **Structured JSON logs** from Lambda shipped to CloudWatch Logs (14-day retention)
- **CloudWatch Dashboard** — Lambda errors, duration p99, throttles; API Gateway 4xx / 5xx; DynamoDB consumed capacity
- **CloudWatch Alarms** — error rate, high latency, throttle count, 5xx rate
- **SNS topic** → email alerts on alarm breach

---

## CI/CD Pipeline

```
Pull Request → pr.yml
  ├── Terraform: fmt + validate + plan (posted as PR comment)
  ├── Backend: pytest (35 unit tests) + Trivy security scan
  ├── Frontend: ESLint + Vite build
  └── pr-ready gate (all jobs must pass)

Merge → develop  →  deploy.yml  →  dev environment     (automatic)
Merge → main     →  deploy.yml  →  production           (manual approval gate)
```

Lambda is cross-compiled for `manylinux2014_x86_64`; boto3 / botocore are stripped from the
package (provided by the Lambda runtime). The frontend builds to hashed asset filenames
(`max-age=31536000`) with `index.html` set to `no-cache`; CloudFront invalidates `/index.html`
only on each deploy.

---

## Infrastructure as Code

All infrastructure is Terraform (v1.15.6), organized into 11 modules:

```
terraform/
├── modules/
│   ├── acm/          # TLS certificates (us-east-1)
│   ├── api_gateway/  # HTTP API v2, custom domain, access logs
│   ├── cloudfront/   # Distribution, OAC, WAF association
│   ├── cloudwatch/   # Dashboard, alarms, SNS topic
│   ├── dynamodb/     # On-demand table, PITR, KMS, TTL
│   ├── github_oidc/  # IAM role for GitHub Actions (OIDC trust)
│   ├── kms/          # CMK, key policy, aliases
│   ├── lambda/       # Function, execution role, log group
│   ├── route53/      # A alias records for both domains
│   ├── s3_frontend/  # SPA bucket, block public access, OAC bucket policy
│   └── s3_reports/   # Reports bucket, lifecycle rules, KMS
├── environments/
│   ├── dev/          # dev.tfvars, backend.hcl, main.tf
│   └── prod/         # prod.tfvars, backend.hcl, main.tf
```

State is stored in S3 with native locking (`use_lockfile = true`, Terraform >= 1.10).

---

*DocImgAnalizer Phase 1 — craftingnewtech.com*
