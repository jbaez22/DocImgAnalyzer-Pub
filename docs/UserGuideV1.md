# DocImgAnalizer — User Guide

## What Is This Service?

DocImgAnalizer is a SaaS tool that analyzes Dockerfiles and Docker image metadata for
security issues, best-practice violations, and quality scoring. It runs entirely serverless
on AWS and requires no installation.

**Endpoints**

| Interface | URL |
|-----------|-----|
| Frontend (browser) | `https://imgapp.craftingnewtech.com` |
| REST API | `https://img.craftingnewtech.com` |

---

## Using the Frontend

Open `https://imgapp.craftingnewtech.com` in your browser.

The home page presents two analysis options:

### Dockerfile Analysis

1. Paste your Dockerfile content into the text area
2. Click **Analyze**
3. The results page displays:
   - **Score** (0–100) — overall quality rating
   - **Findings** — list of rule violations with severity and line references
   - **Fixed Dockerfile** — auto-corrected version with inline annotations
   - **Metadata** — instruction count, stage count, healthcheck presence, multi-stage flag, minimal-base flag

### Image Analysis

1. Enter a Docker image reference in the format `name:tag` or `namespace/name:tag`
2. Click **Analyze**
3. The results page displays:
   - **Image metadata** — name, namespace, tag, digest, architecture, OS
   - **Size** — compressed layer size in MB
   - **Layer count** and **last pushed** date

---

## Using the REST API

All endpoints are under `https://img.craftingnewtech.com/api/v1/`.

### Health Check

Verify the service is up:

```bash
curl https://img.craftingnewtech.com/api/v1/health
```

**Response**
```json
{"status": "ok"}
```

---

### Analyze a Dockerfile

**Request**

```bash
curl -s -X POST https://img.craftingnewtech.com/api/v1/analyze/dockerfile \
  -H "Content-Type: application/json" \
  -d '{
    "content": "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nUSER 1000\nHEALTHCHECK CMD true\nCMD [\"python\", \"main.py\"]"
  }' | jq .
```

**Response**
```json
{
  "scan_id": "a1b2c3d4-...",
  "scan_type": "dockerfile",
  "status": "COMPLETE",
  "score": 90,
  "findings": [
    {
      "rule_id": "R008",
      "severity": "WARNING",
      "title": "Single-stage build — consider multi-stage",
      "description": "A single-stage build ships build tools into the final image.",
      "fix": "FROM <build-image> AS builder\n...\nFROM <minimal-runtime-image>\nCOPY --from=builder /app /app",
      "line": 1
    }
  ],
  "metadata": {
    "instruction_count": 6,
    "stage_count": 1,
    "has_healthcheck": true,
    "has_non_root_user": true,
    "is_multi_stage": false,
    "has_minimal_base": true
  },
  "created_at": "2026-06-19T18:00:00Z",
  "completed_at": "2026-06-19T18:00:00Z"
}
```

---

### Analyze a Docker Image

**Request**

```bash
curl -s -X POST https://img.craftingnewtech.com/api/v1/analyze/image \
  -H "Content-Type: application/json" \
  -d '{"image": "nginx:1.25-alpine"}' | jq .
```

**Response**
```json
{
  "scan_id": "e5f6g7h8-...",
  "scan_type": "image",
  "status": "COMPLETE",
  "score": null,
  "findings": [],
  "metadata": {
    "namespace": "library",
    "name": "nginx",
    "tag": "1.25-alpine",
    "digest": "sha256:abc123...",
    "architecture": "amd64",
    "os": "linux",
    "compressed_size_bytes": 12400000,
    "layer_count": 8,
    "last_pushed": "2024-06-01T00:00:00Z"
  },
  "created_at": "2026-06-19T18:00:01Z",
  "completed_at": "2026-06-19T18:00:01Z"
}
```

---

### Retrieve a Previous Result

Use the `scan_id` returned by any analysis to retrieve the result later:

```bash
curl -s https://img.craftingnewtech.com/api/v1/results/<scan_id> | jq .
```

Results are stored for **90 days** before automatic expiry.

---

## Dockerfile Analysis Rules

Phase 1 implements 11 rules covering the most impactful security and best-practice issues
found in real-world Dockerfiles.

| Rule ID | Severity | Description | Score Deduction |
|---------|----------|-------------|----------------|
| R001 | ERROR | Base image uses `:latest` or has no tag — not pinned to a specific version | -20 per occurrence |
| R002 | ERROR | No `USER` instruction (runs as root), or `USER root` / `USER 0` explicitly set | -25 per occurrence |
| R003 | WARNING | No `HEALTHCHECK` instruction | -10 |
| R004 | ERROR | Secret-like key name in `ENV` or `ARG` (password, token, api_key, etc.) | -30 per occurrence |
| R005 | ERROR | `curl` or `wget` piped directly to `bash`/`sh` — supply-chain risk | -20 per occurrence |
| R006 | WARNING | `ADD` used for local files — prefer `COPY` (ADD has hidden tar-extraction and URL-fetch behaviour) | -5 per occurrence |
| R007 | WARNING | More than one `RUN` instruction — chain with `&&` to reduce image layers | -5 |
| R008 | WARNING | Single-stage build — consider a builder + minimal runtime stage | -10 |
| R009 | WARNING | Final base image is not a minimal variant (not alpine, slim, distroless, Chainguard, or scratch) | -10 |
| R010 | WARNING | Package manager cache not cleaned: `apt-get` without `rm -rf /var/lib/apt/lists/*`, `pip` without `--no-cache-dir`, or `apk` without `--no-cache` | -10 (once total) |
| R011 | WARNING | `npm install` used instead of `npm ci` — `npm ci` enforces lock-file and is reproducible | -5 (once total) |

### Severity Levels

| Severity | Meaning |
|----------|---------|
| `ERROR` | Security risk — must be fixed before production |
| `WARNING` | Best-practice violation — strongly recommended to fix |
| `INFO` | Informational — consider as improvement |

### Scoring

The score starts at 100 and deductions are applied per finding as listed in the table above.
Score is clamped to the range 0–100.

**Notes on deduction counting:**
- R010 and R011 deduct points **once** regardless of how many offending `RUN` lines exist.
  Each offending line still produces a separate Finding (with its line number), so all
  issues are visible — but the score only loses points once per rule.
- All other rules deduct per occurrence.

**Score bands**

| Score | Rating |
|-------|--------|
| 90–100 | Excellent |
| 70–89 | Good |
| 50–69 | Needs improvement |
| 0–49 | Poor — significant issues present |

---

## Dockerfile Examples

### Well-written Dockerfile (score 90)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 1000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Passes:** R001 (tag pinned), R002 (non-root user), R003 (HEALTHCHECK present),
R009 (`slim` = minimal base), R010 (`--no-cache-dir` present).

**R008 warning triggered** (single-stage build) — deducts 10 points → score 90.
To reach 100, split into a multi-stage build.

### Ideal Dockerfile (score 100)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
USER 1000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- Pinned base image tag (`python:3.12-slim`)
- Multi-stage build (builder + runtime stages) — passes R008
- Minimal base (`slim`) — passes R009
- pip with `--no-cache-dir` — passes R010
- Non-root USER — passes R002
- HEALTHCHECK present — passes R003
- Single RUN per stage — passes R007
- No ENV/ARG secrets — passes R004

### Low-scoring Dockerfile (score 0)

```dockerfile
FROM python
RUN apt-get update
RUN pip install requests
RUN pip install boto3
ENV PASSWORD=mysecret
ADD . /app
```

Findings triggered:

| Rule | Finding |
|------|---------|
| R001 | `python` has no tag |
| R002 | No USER instruction |
| R003 | No HEALTHCHECK |
| R004 | `PASSWORD` in ENV |
| R006 | ADD instead of COPY |
| R007 | 3 RUN instructions |
| R008 | Single-stage build |
| R009 | `python` is not a minimal base |
| R010 | `pip install requests` and `pip install boto3` have no `--no-cache-dir` |

Total deductions exceed 100 → score clamped to 0.

---

## Image Reference Formats

The image analysis endpoint accepts standard Docker image reference formats:

| Format | Example |
|--------|---------|
| Official image with tag | `nginx:1.25-alpine` |
| Official image latest | `nginx:latest` |
| Namespaced image | `bitnami/nginx:1.25` |
| Digest-pinned | `nginx@sha256:abc123...` |

Only **public Docker Hub** images are supported in Phase 1. Private registries and other
registries (ECR, GCR, GHCR) are out of scope until Phase 2.

---

## Error Responses

| HTTP Status | Meaning |
|-------------|---------|
| 200 | Success |
| 404 | Scan ID not found, or image not found on Docker Hub |
| 422 | Invalid request body (empty content, missing fields) |
| 502 | Upstream error reaching Docker Hub registry |

**Example 404 response**
```json
{"detail": "Image 'nobody/fake:v9' not found on Docker Hub."}
```

**Example 422 response**
```json
{
  "detail": [
    {
      "loc": ["body", "content"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Data Retention

| Data | Retention |
|------|-----------|
| Scan results (DynamoDB) | 90 days — automatic TTL expiry |
| Full JSON reports (S3) | No automatic expiry in Phase 1 |
| CloudWatch logs | 14 days |

---

## UI Test Cases

The following test cases cover the main user scenarios. Run them in order to validate
the full flow from submission through results retrieval.

---

### Test Case 1 — Dockerfile: High Score with Multi-Stage Build

**Goal:** Verify a well-written multi-stage Dockerfile scores 100 with no findings.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Dockerfile Analysis**
3. Paste the content below into the text area
4. Click **Analyze**

**Input:**
```dockerfile
FROM node:20.14-alpine AS builder
WORKDIR /build
COPY package*.json ./
RUN npm ci --only=production

FROM node:20.14-alpine
WORKDIR /app
COPY --from=builder /build/node_modules ./node_modules
COPY . .
USER 1000
HEALTHCHECK CMD wget -qO- http://localhost:3000/health || exit 1
CMD ["node", "server.js"]
```

**Expected result:**
- Status: `COMPLETE`
- Score: 100
- Findings: none
- Metadata: `has_healthcheck: true`, `is_multi_stage: true`, `has_minimal_base: true`, `stage_count: 2`

---

### Test Case 2 — Dockerfile: Single-Stage Warning (R008)

**Goal:** Verify that a single-stage Dockerfile triggers R008 even when all other rules pass.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Dockerfile Analysis**
3. Paste the content below
4. Click **Analyze**

**Input:**
```dockerfile
FROM node:20.14-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
USER 1000
HEALTHCHECK CMD wget -qO- http://localhost:3000/health || exit 1
CMD ["node", "server.js"]
```

**Expected result:**
- Status: `COMPLETE`
- Score: 90
- Findings: exactly one finding — R008 (`WARNING`)
- Metadata: `is_multi_stage: false`, `has_minimal_base: true`

---

### Test Case 3 — Dockerfile: Multiple Security Violations

**Goal:** Verify detection of a poorly written Dockerfile covering rules R001–R010.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Dockerfile Analysis**
3. Paste the content below
4. Click **Analyze**

**Input:**
```dockerfile
FROM ubuntu
RUN apt-get update
RUN apt-get install -y curl
RUN apt-get install -y python3
ENV DB_PASSWORD=supersecret123
ENV API_KEY=abc-xyz-000
ADD . /app
```

**Expected result:**
- Status: `COMPLETE`
- Score: 0 (clamped — total deductions exceed 100)
- Findings must include:
  - R001 — unpinned base image (`ubuntu` with no tag) — ERROR
  - R002 — no USER instruction — ERROR
  - R003 — no HEALTHCHECK — WARNING
  - R004 — secrets in ENV (`DB_PASSWORD`, `API_KEY`) — ERROR (×2)
  - R006 — ADD instead of COPY — WARNING
  - R007 — 3 RUN instructions — WARNING
  - R008 — single-stage build — WARNING
  - R009 — `ubuntu` is not a minimal base — WARNING
  - R010 — `apt-get install` without `rm -rf /var/lib/apt/lists/*` — WARNING

---

### Test Case 4 — Dockerfile: Pipe Install Detection (R005)

**Goal:** Verify that `curl | bash` is detected as an error-level supply-chain risk.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Dockerfile Analysis**
3. Paste the content below
4. Click **Analyze**

**Input:**
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y curl
RUN curl -fsSL https://get.docker.com | bash
USER 1000
HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1
CMD ["/usr/bin/dockerd"]
```

**Expected result:**
- Status: `COMPLETE`
- Findings must include:
  - R005 — pipe-install (`curl ... | bash`) — ERROR
  - R007 — 2 RUN instructions — WARNING
  - R008 — single-stage build — WARNING
  - R009 — `ubuntu:22.04` is not a minimal base — WARNING
  - R010 — `apt-get install` without cache cleanup — WARNING
- R001, R002, R003 must NOT be triggered (base image is pinned, USER is set, HEALTHCHECK is present)

---

### Test Case 5 — Dockerfile: Package Cache Cleanup (R010)

**Goal:** Verify all three package managers (apt, pip, apk) are detected when cache is not cleaned.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Dockerfile Analysis**
3. Paste the content below
4. Click **Analyze**

**Input:**
```dockerfile
FROM python:3.12-alpine
RUN apk add curl
RUN pip install requests
USER 1000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "app.py"]
```

**Expected result:**
- Status: `COMPLETE`
- Findings must include:
  - R007 — 2 RUN instructions (WARNING)
  - R008 — single-stage build (WARNING)
  - R010 — `apk add` without `--no-cache` (WARNING)
  - R010 — `pip install` without `--no-cache-dir` (WARNING)
- R001, R002, R003, R009 must NOT be triggered (tag pinned, USER set, HEALTHCHECK present, `alpine` = minimal)
- Score: 100 − 5 (R007) − 10 (R008) − 10 (R010, once) = **75**

---

### Test Case 6 — Dockerfile: npm ci vs npm install (R011)

**Goal:** Verify that `npm install` is flagged and `npm ci` is accepted.

**Part A — Flagged:**

**Input:**
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
USER 1000
HEALTHCHECK CMD wget -qO- http://localhost:3000/health || exit 1
CMD ["node", "server.js"]
```

**Expected result:**
- Findings must include R011 — `npm install` instead of `npm ci` (WARNING)
- Fixed Dockerfile must show `npm ci` replacing `npm install`

**Part B — Accepted:**

Replace `RUN npm install` with `RUN npm ci` and re-analyze.

**Expected result:**
- R011 must NOT be present in findings
- Score improvement of 5 points compared to Part A

---

### Test Case 7 — Dockerfile: Minimal Base Image (R009)

**Goal:** Verify R009 triggers for bloated base images and does not trigger for minimal ones.

**Part A — Triggers R009 (ubuntu:22.04):**

**Input:**
```dockerfile
FROM ubuntu:22.04
WORKDIR /app
COPY . .
USER 1000
HEALTHCHECK CMD curl -f http://localhost/health || exit 1
CMD ["/app/server"]
```

**Expected result:**
- Findings must include R009 — `ubuntu:22.04` is not a minimal base (WARNING)
- Metadata: `has_minimal_base: false`

**Part B — Does NOT trigger R009 (alpine):**

Replace `FROM ubuntu:22.04` with `FROM alpine:3.20` and re-analyze.

**Expected result:**
- R009 must NOT be present in findings
- Metadata: `has_minimal_base: true`

---

### Test Case 8 — Image Analysis: Public Docker Hub Image

**Goal:** Verify that metadata for a well-known public image is retrieved correctly.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Image Analysis**
3. Enter `nginx:1.25-alpine` in the image field
4. Click **Analyze**

**Expected result:**
- Status: `COMPLETE`
- Metadata fields populated:
  - `name`: `nginx`
  - `namespace`: `library`
  - `tag`: `1.25-alpine`
  - `digest`: non-empty `sha256:...` string
  - `architecture`: `amd64`
  - `os`: `linux`
  - `layer_count`: > 0
  - `compressed_size_bytes`: > 0

---

### Test Case 9 — Image Analysis: Non-existent Image (Error Handling)

**Goal:** Verify a clear error is returned when an image does not exist on Docker Hub.

**Steps:**
1. Open `https://imgapp.craftingnewtech.com`
2. Select **Image Analysis**
3. Enter `thisuser/doesnotexist:v999` in the image field
4. Click **Analyze**

**Expected result:**
- The UI displays an error message (not a blank page or spinner)
- HTTP status returned by the API: `404`
- Error detail indicates the image was not found

---

## Limitations (Phase 1)

- **Dockerfile analysis** uses a built-in rule engine (11 rules). Deep linting via Hadolint
  or Trivy is planned for Phase 2.
- **Image analysis** returns metadata only — no CVE scanning, no layer inspection.
  Full image scanning with Trivy/Syft is planned for Phase 2.
- **Authentication** is not required in Phase 1 (open MVP). Rate limiting is enforced
  at the WAF layer (1000 requests per 5 minutes per IP).
- **Docker Hub only** — private registries and alternative registries are not supported.
- **Scan history** is not tied to a user identity — results are accessible by `scan_id`
  only. User accounts via Cognito are planned for Phase 2.
