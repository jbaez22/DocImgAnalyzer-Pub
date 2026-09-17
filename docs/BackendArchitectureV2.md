# Backend Architecture — DocImgAnalizer Phase 2

## Overview

Phase 2 introduces two new compute components:

1. **Lambda v2** — FastAPI v2 application (`backend/v2/`) handling authenticated API routes,
   JWT validation, and SQS job dispatch. Deployed as `img-analyzer-{env}-api-v2`.
2. **ECS Fargate Scanner** — containerized Python script (`backend/scanner/`) running Trivy
   and Syft inside a VPC private subnet. Triggered by SQS messages via EventBridge Pipes.

**Phase 1 Lambda (`backend/app/main.py`) is frozen** — it continues to handle all `/api/v1/`
routes unchanged and is never modified by Phase 2.

---

## Lambda v2 Runtime Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Runtime | Python | 3.12 |
| Web framework | FastAPI | 0.115.5 |
| ASGI adapter | Mangum | 0.19.0 |
| Data validation | Pydantic v2 | 2.10.x |
| JWT validation | python-jose[cryptography] | 3.x |
| AWS SDK | boto3 | 1.35.81 |

### Request Path

```
API Gateway event
       │
  JWT Authorizer ──► Cognito JWKS endpoint (validates RS256 signature)
       │ (request rejected with 401 if invalid)
       ▼
     Mangum  ──► FastAPI v2 app
       │
  get_current_user() ──► extracts sub, email from JWT claims
       │
  Router handler
  ├── analyze/dockerfile → reuses Phase 1 rule engine
  └── analyze/image      → write PENDING to DDB v2 → send SQS → return 202
```

---

## Application Structure

```
backend/v2/
├── main.py                   # FastAPI app, router includes, Mangum handler
├── routers/
│   ├── analyze.py            # POST /analyze/dockerfile, POST /analyze/image
│   ├── results.py            # GET /results/{scan_id}
│   └── scans.py              # GET /scans, DELETE /scans/{scan_id}
├── auth/
│   └── cognito.py            # JWT validation helper + get_current_user() FastAPI dependency
├── services/
│   ├── sqs_producer.py       # enqueue_scan() — publish to SQS
│   └── scan_status.py        # update_status(), get_status() — DynamoDB helpers
├── models/
│   └── schemas.py            # Pydantic request/response schemas
└── db/
    └── dynamodb.py           # get_scan(), list_user_scans(), put_scan(), delete_scan()
```

### JWT Validation

API Gateway validates the Cognito JWT before Lambda is invoked (RS256, JWKS endpoint).
The `get_current_user()` FastAPI dependency is a secondary guard that extracts claims
(user `sub`, email) from the pre-verified token in the Lambda event context.

```python
# auth/cognito.py
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    # fetch JWKS, decode with python-jose, return claims
    claims = jwt.decode(token, jwks, algorithms=["RS256"],
                        audience=COGNITO_CLIENT_ID)
    return claims
```

All route handlers receive `user: dict` from this dependency — `user["sub"]` is the
Cognito user UUID used as `user_id` in DynamoDB.

---

## ECS Fargate Scanner

### Container Stack

| Component | Technology |
|-----------|-----------|
| Base image | `aquasec/trivy:latest` → copied to `python:3.12-slim` |
| CVE scanner | Trivy (bundled in base image) |
| SBOM generator | Syft (installed from installer script at build time) |
| Runtime | Python 3.12 |
| Entry point | `scan.py` |

### Scanner Lifecycle

```
EventBridge Pipe polls SQS (batch size: 1)
         │
         ▼
ECS launches Fargate task
  env: SQS_MESSAGE = { scan_id, image_name, user_id }
         │
         ├── 1. update DynamoDB: status = PROCESSING
         │
         ├── 2. trivy image <image_name> --format json
         │       ▼
         │    parse CVE count by severity
         │
         ├── 3. syft <image_name> -o cyclonedx-json
         │       ▼
         │    CycloneDX SBOM JSON
         │
         ├── 4. upload CVE JSON  → s3://img-analyzer-{env}-cve-reports/{scan_id}/
         │    upload SBOM JSON  → s3://img-analyzer-{env}-sbom-reports/{scan_id}/
         │
         └── 5. update DynamoDB: status = COMPLETE
                  cve_critical, cve_high, cve_medium, cve_low
                  report_s3_key, sbom_s3_key
```

**Error handling:** If `scan.py` exits with a non-zero status code, the Fargate task
fails. After `max_receive_count` (3) delivery attempts, SQS moves the message to the DLQ.
The CloudWatch alarm triggers, and the SNS topic sends an email alert.

### Networking

Fargate tasks run in private subnets with no public IP. All AWS API calls route through
VPC Interface Endpoints:

- ECR DKR + ECR API — pull scanner image
- SQS — receive/delete message
- CloudWatch Logs — stream container output
- S3 Gateway Endpoint — write CVE/SBOM reports
- DynamoDB Gateway Endpoint — update scan status

---

## DynamoDB v2 Access Patterns

| Operation | Access pattern |
|-----------|---------------|
| Write new scan (Lambda v2) | `put_item` on `scan_id` (PK) |
| Poll scan status (Lambda v2) | `get_item` by `scan_id` |
| Update scan on completion (Fargate) | `update_item` by `scan_id` |
| List user history (Lambda v2) | `query` on `user-scans-index` GSI, PK = `user_id` |
| Delete scan (Lambda v2) | `delete_item` by `scan_id` (after verifying `user_id`) |

**User isolation:** `list_user_scans()` always filters by the `user_id` extracted from the
JWT `sub` claim. Direct `scan_id` lookups verify `item["user_id"] == jwt_sub` before
returning data.

---

## IAM Role Summary

| Role | Principal | Access |
|------|-----------|--------|
| `img-analyzer-{env}-phase2-lambda-exec` | Lambda | DDB v2 read/write, SQS send, S3 get, KMS |
| `img-analyzer-{env}-phase2-fargate-task` | ECS Tasks | SQS receive/delete, DDB v2 write, S3 put, KMS |
| `img-analyzer-{env}-phase2-fargate-exec` | ECS Tasks | ECR pull, CloudWatch Logs, KMS |
| `img-analyzer-{env}-phase2-github-actions` | GitHub OIDC | Lambda update, ECR push, ECS task register, TF state |

**None of these roles has access to Phase 1 resources** (Phase 1 DynamoDB table,
Phase 1 S3 buckets, Phase 1 Lambda function).

---

## Environment Variables

### Lambda v2

| Variable | Source | Description |
|----------|--------|-------------|
| `COGNITO_USER_POOL_ID` | Terraform output | Validates JWT issuer |
| `COGNITO_CLIENT_ID` | Terraform output | Validates JWT audience |
| `SQS_QUEUE_URL` | Terraform output | Queue to publish scan jobs |
| `DYNAMODB_TABLE` | Terraform output | DynamoDB v2 table name |
| `REPORTS_BUCKET` | Terraform output | CVE reports S3 bucket |
| `SBOM_BUCKET` | Terraform output | SBOM S3 bucket |
| `ENVIRONMENT` | tfvars | `dev` or `prod` |

### Fargate Scanner

| Variable | Source | Description |
|----------|--------|-------------|
| `DYNAMODB_TABLE` | ECS task definition | DynamoDB v2 table name |
| `REPORTS_BUCKET` | ECS task definition | CVE reports S3 bucket |
| `SBOM_BUCKET` | ECS task definition | SBOM S3 bucket |
| `SQS_MESSAGE` | EventBridge Pipe override | The raw SQS message body (JSON) |
| `AWS_DEFAULT_REGION` | ECS task definition | AWS region |

---

## Build and Deploy

### Lambda v2

Lambda is cross-compiled for `manylinux2014_x86_64` (matching the Lambda execution
environment). `boto3` and `botocore` are excluded from the package — the Lambda runtime
provides them.

```bash
pip install --platform manylinux2014_x86_64 --only-binary=:all: \
  --target backend/v2/package -r backend/requirements.txt
cp -r backend/v2 backend/v2/package/
cd backend/v2/package && zip -r ../../../../lambda-v2.zip .
aws lambda update-function-code --function-name img-analyzer-dev-api-v2 \
  --zip-file fileb://lambda-v2.zip
```

The Lambda alias `v2` always points to `$LATEST`. The API Gateway route targets the alias
ARN so the live alias is always reachable.

### Scanner Container

```bash
docker build --platform linux/amd64 -t img-analyzer-dev-scanner:latest backend/scanner/
docker tag img-analyzer-dev-scanner:latest <ecr-url>:latest
docker push <ecr-url>:latest
```

After pushing, register a new ECS task definition revision:

```bash
aws ecs register-task-definition --cli-input-json file://task-def.json
```

The EventBridge Pipe always launches the `LATEST` task definition revision.

---

*DocImgAnalizer Phase 2 — craftingnewtech.com*
