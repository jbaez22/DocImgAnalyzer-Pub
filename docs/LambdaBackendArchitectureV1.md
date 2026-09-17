# Lambda Backend Architecture — DocImgAnalizer Phase 1

## Overview

The backend is a Python 3.12 FastAPI application deployed as an AWS Lambda function.
It receives HTTP requests from API Gateway HTTP API v2, performs analysis entirely
in-memory (no containers, no external scanners), persists results to DynamoDB and S3,
and returns a structured JSON response.

There are no third-party security scanners (Hadolint, Trivy, Syft) in Phase 1.
All analysis logic is custom Python code built into the Lambda package.

---

## Runtime Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Runtime | Python | 3.12 | Lambda execution environment |
| Web framework | FastAPI | 0.115.5 | Route handling, request validation, OpenAPI |
| ASGI adapter | Mangum | 0.19.0 | Translates API Gateway events into ASGI requests |
| Data validation | Pydantic | 2.10.3 | Request/response schemas and type enforcement |
| HTTP client | httpx | 0.28.1 | Calls Docker Hub API for image metadata |
| AWS SDK | boto3 | 1.35.81 | DynamoDB + S3 operations |
| Logging | python-json-logger | 2.0.7 | Structured JSON logs to CloudWatch |

### Why Mangum?

Lambda receives events as raw Python dicts (API Gateway proxy format).
FastAPI expects standard ASGI calls. Mangum sits between them:

```
API Gateway event (dict)
        |
      Mangum          ← translates event → ASGI scope + receive/send callables
        |
    FastAPI app       ← handles the request normally
        |
      Mangum          ← translates ASGI response → API Gateway response dict
        |
API Gateway response (dict)
```

This means FastAPI can be developed and tested locally with `uvicorn` exactly as any
other web app, and deployed to Lambda with zero code changes.

---

## Application Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORSMiddleware, Mangum handler
│   ├── routers/
│   │   ├── analyze.py           # POST /analyze/dockerfile, POST /analyze/image
│   │   └── results.py           # GET /results/{scan_id}
│   ├── services/
│   │   ├── dockerfile_analyzer.py   # Custom rule engine (no external tools)
│   │   └── image_analyzer.py        # Docker Hub API client
│   ├── models/
│   │   └── schemas.py           # Pydantic models: Finding, AnalysisReport, etc.
│   └── db/
│       └── dynamodb.py          # DynamoDB read/write wrapper
```

---

## Request Flow

```
Browser
  |
  | POST /api/v1/analyze/dockerfile
  v
API Gateway HTTP API v2
  |
  | Lambda proxy integration (payload format 2.0)
  v
Lambda Function (img-analyzer-<env>-api)
  |
  | Mangum translates event → ASGI
  v
FastAPI router (analyze.py)
  |
  |── 1. Validate request (Pydantic)
  |── 2. Run analysis service (dockerfile_analyzer or image_analyzer)
  |── 3. Build AnalysisReport
  |── 4. Store full report to S3 (reports/<scan_id>.json)
  |── 5. Write scan record to DynamoDB
  |── 6. Return AnalysisReport JSON
  v
API Gateway HTTP API v2
  |
  v
Browser
```

---

## Dockerfile Analysis — How It Works

**No external tools are used.** The entire analysis is a custom Python rule engine
in `app/services/dockerfile_analyzer.py`.

### Step 1 — Parse the Dockerfile

The parser reads the raw Dockerfile text line by line, handles line continuations
(trailing `\`), skips comments, and produces a list of `(instruction, arguments, line_number)` tuples:

```python
[
  ("FROM",        "python:3.12-slim",   1),
  ("WORKDIR",     "/app",               2),
  ("COPY",        ". .",                3),
  ("USER",        "1000",               4),
  ("HEALTHCHECK", "CMD ...",            5),
  ("CMD",         '["python", "main.py"]', 6),
]
```

**No external Dockerfile parser library is used.** The parser is ~20 lines of pure
Python. It correctly handles multi-line instructions like:

```dockerfile
RUN apt-get update && \
    apt-get install -y curl
```

### Step 2 — Run Rules

Each rule is a standalone check against the parsed instruction list. Rules are
independent — a failure in one does not affect others.

| Rule | Detection Method | Packages Used |
|------|-----------------|---------------|
| R001 | Check each FROM instruction: no `:` in image ref, or ends with `:latest` | None — string operations |
| R002 | Count USER instructions; check if value is `root` or `0` | None — string comparison |
| R003 | Check if `HEALTHCHECK` appears in the instruction name list | None — list membership |
| R004 | Check ENV/ARG key names against a regex pattern of secret-like words | `re` (stdlib) |
| R005 | Check RUN args for `curl`/`wget` piped to `bash`/`sh` | `re` (stdlib) |
| R006 | Check ADD instructions for local paths (no `http://` or `https://`) | `re` (stdlib) |
| R007 | Count total RUN instructions; flag if more than 1 | None — list count |
| R008 | Count FROM instructions; flag if only 1 and base is not `scratch` | None — list count |
| R009 | Check final FROM base image against known minimal keywords (alpine, slim, distroless, chainguard, busybox, scratch) | None — string search |
| R010 | Check each RUN for `apt-get install` without cleanup, `pip install` without `--no-cache-dir`, `apk add` without `--no-cache` | `re` (stdlib) |
| R011 | Check each RUN for `npm install` without a matching `npm ci` | `re` (stdlib) |

**The only library used for analysis is Python's built-in `re` module.**
No pip packages are involved in the analysis logic itself.

### Secret Pattern (R004)

```python
_SECRET_PATTERN = re.compile(
    r"\b(password|passwd|pwd|secret|token|api_key|apikey|credential|private_key|access_key)\b",
    re.IGNORECASE,
)
```

Matched against the **key name** only (left side of `=`), not the value.
This avoids false positives from values that happen to contain those words.

### Pipe Install Pattern (R005)

```python
_PIPE_INSTALL_PATTERN = re.compile(r"(curl|wget).+\|\s*(ba)?sh", re.IGNORECASE)
```

Detects `curl ... | bash`, `curl ... | sh`, `wget ... | bash`, etc.

### Step 3 — Score Calculation

Score starts at 100. Each finding deducts points based on severity:

| Rule | Deduction |
|------|-----------|
| R001 | -20 per occurrence |
| R002 | -25 per occurrence |
| R003 | -10 |
| R004 | -30 per occurrence |
| R005 | -20 per occurrence |
| R006 | -5 per occurrence |
| R007 | -5 |
| R008 | -10 |
| R009 | -10 |
| R010 | -10 (once total; multiple Findings emitted per offending line) |
| R011 | -5 (once total; multiple Findings emitted per offending line) |

```python
result.score = max(0, 100 - deductions)
```

Score is clamped to `[0, 100]`.

### Step 4 — Fixed Dockerfile Generation

If any findings exist, the analyzer generates a `fixed_dockerfile` string by applying
rule-based transformations to the original content:

| Rule | Transformation Applied |
|------|----------------------|
| R001 | Replace `FROM image` with `FROM image:<specific-version>` + comment |
| R002 | Insert `USER 1000` before the last CMD/ENTRYPOINT (or at end) |
| R003 | Insert `HEALTHCHECK ...` before the last CMD/ENTRYPOINT (or at end) |
| R004 | Comment out secret ENV/ARG lines with an explanation |
| R005 | Comment out the unsafe line; add a checksum-verification template above |
| R006 | Replace `ADD <args>` with `COPY <args>` |
| R007 | Consolidate consecutive RUN instructions with `&&` chaining |
| R008 | Prepend a header comment with a multi-stage build example template |
| R009 | Prepend a header comment suggesting minimal base image alternatives |
| R010 | Inline `--no-cache-dir` into `pip install`; inline `--no-cache` into `apk add`; add advisory comment above `apt-get install` lines |
| R011 | Replace `npm install` with `npm ci` in-place |

The generator runs in four passes so fixes compose correctly and do not interfere with
each other. R008/R009 prepend structural guidance as header comments; R007 consolidation
operates on the already line-fixed output of Pass 1.

---

## Image Analysis — How It Works

**No image is pulled.** The image analyzer calls the Docker Hub public REST API
to retrieve metadata only.

### Docker Hub API Call

```
GET https://hub.docker.com/v2/repositories/{namespace}/{name}/tags/{tag}/
```

- Official images (e.g. `nginx`) use namespace `library`
- User images (e.g. `bitnami/nginx`) use the specified namespace
- The endpoint is public and requires no authentication for public images

### Image Reference Parsing

```python
'nginx'              → ('library', 'nginx',  'latest')
'nginx:1.25-alpine'  → ('library', 'nginx',  '1.25-alpine')
'user/repo:v1.0'     → ('user',    'repo',   'v1.0')
```

### Data Extracted

From the API response:

| Field | Source in API response |
|-------|----------------------|
| `digest` | `images[].digest` (prefers `amd64` architecture) |
| `architecture` | `images[].architecture` |
| `os` | `images[].os` |
| `compressed_size_bytes` | `images[].size` |
| `layer_count` | `len(images[].layers)` |
| `last_pushed` | `last_pushed` |

### HTTP Client

`httpx` is used instead of `requests` for its async capability (ready for future
async refactor) and its cleaner timeout/redirect API:

```python
with httpx.Client(timeout=10.0, follow_redirects=True) as client:
    response = client.get(url)
    response.raise_for_status()
```

Error handling:
- `404` → `ValueError` → API returns HTTP 404
- Any other HTTP error → `RuntimeError` → API returns HTTP 502
- Network timeout/connection error → `RuntimeError` → API returns HTTP 502

---

## Data Persistence

### DynamoDB

Each scan is written as a single item with:

| Attribute | Type | Notes |
|-----------|------|-------|
| `scan_id` | String | Partition key — UUID v4 |
| `created_at` | String | Sort key — ISO 8601 UTC |
| `scan_type` | String | `dockerfile` or `image` |
| `status` | String | `COMPLETE` or `FAILED` |
| `score` | Number | 0–100 (Dockerfile only) |
| `findings` | List | Serialized Finding objects |
| `metadata` | Map | Instruction counts / image metadata |
| `report_s3_key` | String | S3 key of full JSON report |
| `ttl` | Number | Unix epoch — auto-expires after 90 days |

The DynamoDB client uses lazy initialization — the boto3 resource is created on first
use and cached for the lifetime of the Lambda execution context (warm starts reuse it).

### S3 Reports Bucket

The full `AnalysisReport` JSON (including `fixed_dockerfile`) is stored at:

```
reports/<scan_id>.json
```

This preserves the complete result indefinitely, even after the DynamoDB TTL expires.

---

## CORS Handling

The FastAPI app uses `CORSMiddleware` to handle browser preflight requests:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "https://imgapp.craftingnewtech.com")],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)
```

The allowed origin is read from a Lambda environment variable set by Terraform —
it differs between dev (`https://dev-imgapp.craftingnewtech.com`) and prod
(`https://imgapp.craftingnewtech.com`).

**Why middleware and not API Gateway CORS?** API Gateway HTTP API v2 `cors_configuration`
adds the correct response headers but still forwards OPTIONS preflight requests to Lambda
via the `$default` catch-all route. Without `CORSMiddleware`, FastAPI returns 405 on
OPTIONS, causing the browser to block all subsequent requests.

---

## Environment Variables

All configuration is injected by Lambda environment variables set in Terraform:

| Variable | Value | Purpose |
|----------|-------|---------|
| `ENVIRONMENT` | `dev` / `prod` | Runtime environment label |
| `DYNAMODB_TABLE_NAME` | `img-analyzer-<env>-scans` | DynamoDB table to read/write |
| `REPORTS_BUCKET_NAME` | `img-analyzer-<env>-reports` | S3 bucket for full reports |
| `ALLOWED_ORIGIN` | `https://imgapp.craftingnewtech.com` | CORS allowed origin |
| `DYNAMODB_TTL_DAYS` | `90` | Scan record expiry in days |
| `LOG_LEVEL` | `INFO` (prod) / `DEBUG` (dev) | CloudWatch log verbosity |

---

## Phase 2 — Planned Improvements

The custom rule engine in Phase 1 covers 11 rules with regex and string matching.
Phase 2 will replace or augment it with:

| Tool | What It Adds |
|------|-------------|
| **Trivy** | CVE scanning of base images, OS packages, language dependencies — runs in a Fargate container (Lambda has a 15-min timeout and no container runtime) |
| **Hadolint** | 80+ Dockerfile lint rules including shell best practices, apt/yum patterns, and label conventions |
| **Syft** | Software Bill of Materials (SBOM) generation — lists all packages in an image |

The Lambda will remain the API entry point but will dispatch long-running scans to SQS,
with Fargate workers consuming the queue. The client polls `/results/{scan_id}` until
status changes from `PENDING` to `COMPLETE`.
