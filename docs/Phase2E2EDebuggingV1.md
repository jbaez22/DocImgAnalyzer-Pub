# Phase 2 E2E Validation — Issues & Fixes

**Sessions**: 2026-07-06 / 2026-07-07  
**Branch**: `phase2` — merged to `develop` at `94f37d4`  
**Status**: COMPLETE — full E2E smoke test passed 2026-07-07

---

## Architecture Under Test

```
User → POST /api/v2/analyze/image
     → Lambda v2 (ecs_launcher.launch_scan)
     → ECS RunTask (Fargate, private subnet)
     → Scanner container (Trivy + Syft)
     → DynamoDB v2 (status: PENDING → PROCESSING → COMPLETE)
     → S3 (CVE report + SBOM)
```

All AWS traffic routes through VPC endpoints — no NAT Gateway, no internet egress.

---

## Issue Log

### Issue 1 — `CannotPullContainerError` (S3 egress blocked)

**Symptom**  
Fargate task fails immediately: `dial tcp ABC-EXAMPLE-XXXX:443: i/o timeout`

**Root Cause**  
ECR DKR serves the image manifest via the `ecr.dkr` VPC Interface Endpoint. However, ECR stores layer blobs in S3 and issues a 307 redirect to an S3 URL. S3 uses a **Gateway endpoint** (no ENI), so a security-group reference to the VPC endpoints SG does not cover it. The Fargate task SG had no rule for the S3 prefix list.

**Fix** — `terraform/phase2/modules/vpc/main.tf`  
Added second egress block to `aws_security_group.fargate_task`:
```hcl
data "aws_ec2_managed_prefix_list" "s3" {
  name = "com.amazonaws.${data.aws_region.current.name}.s3"
}

egress {
  from_port       = 443
  to_port         = 443
  protocol        = "tcp"
  prefix_list_ids = [data.aws_ec2_managed_prefix_list.s3.id]
}
```
Applied live: `terraform apply -target=module.vpc`

---

### Issue 2 — `KeyError: 'scan_id'` (stale scanner image)

**Symptom**  
Scanner task exits with `KeyError: 'scan_id'` — old code path reading from SQS JSON message.

**Root Cause**  
The Docker image tagged `env-vars` was built before `scan.py` was updated to use `os.environ["SCAN_ID"]` / `os.environ["IMAGE_NAME"]`. The build used the old source.

**Fix** — `backend/scanner/scan.py`  
```python
# Before (SQS-era code):
scan_id = message["scan_id"]

# After (Lambda RunTask env vars):
scan_id = os.environ["SCAN_ID"]
image_name = os.environ["IMAGE_NAME"]
```
Rebuilt and pushed as image tag `v3`, registered as task definition revision 10.

---

### Issue 3 — `import json` missing

**Symptom**  
`json.loads()` used in `run_trivy()` and `run_syft()` but `import json` was removed in a previous cleanup.

**Fix** — `backend/scanner/scan.py`  
Added `import json` back to the imports block.

---

### Issue 4 — DynamoDB timeout (`Connect timeout on dynamodb.us-east-1.amazonaws.com`)

**Symptom**  
Scanner reaches `update_status(scan_id, "PROCESSING")` and hangs for 60 seconds then times out. Task ran with no CloudWatch Logs output because the AWSLOGS driver was buffering during the hang.

**Root Cause**  
DynamoDB uses a **Gateway endpoint** (same as S3) — no ENI, no security group reference. The Fargate task SG allowed egress to the VPC endpoints SG (covering ECR, SQS, CloudWatch Logs interface endpoints) and to the S3 prefix list, but had **no rule for the DynamoDB prefix list** (`pl-02cd2c6b`). Traffic to DynamoDB public IPs was dropped.

**Fix** — `terraform/phase2/modules/vpc/main.tf`  
Added third egress block to `aws_security_group.fargate_task`:
```hcl
data "aws_ec2_managed_prefix_list" "dynamodb" {
  name = "com.amazonaws.${data.aws_region.current.name}.dynamodb"
}

egress {
  from_port       = 443
  to_port         = 443
  protocol        = "tcp"
  prefix_list_ids = [data.aws_ec2_managed_prefix_list.dynamodb.id]
}
```
Applied live via `aws ec2 authorize-security-group-egress`.

**Key Lesson**  
VPC Gateway endpoints (S3, DynamoDB) differ from Interface endpoints: they use route table entries for routing but **security groups at the source ENI still evaluate the outbound traffic**. Both must be covered with prefix list rules, not security group references.

---

### Issue 5 — `error` is a DynamoDB reserved keyword

**Symptom**  
`ValidationException: Invalid UpdateExpression: Attribute name is a reserved keyword; reserved keyword: error` when scanner calls `update_status(scan_id, "FAILED", error=str(exc))`.

**Fix** — `backend/scanner/scan.py`  
Updated `update_status()` to wrap reserved attribute names in `ExpressionAttributeNames`:
```python
_RESERVED = {"error", "name", "status", "type", "value", "timestamp"}

def update_status(scan_id: str, status: str, **attrs) -> None:
    update_expr = "SET #s = :s, updated_at = :u"
    expr_names = {"#s": "status"}
    expr_values = {":s": status, ":u": datetime.now(timezone.utc).isoformat()}
    for k, v in attrs.items():
        if k in _RESERVED:
            placeholder = f"#attr_{k}"
            expr_names[placeholder] = k
            update_expr += f", {placeholder} = :{k}"
        else:
            update_expr += f", {k} = :{k}"
        expr_values[f":{k}"] = v
    _table.update_item(
        Key={"scan_id": scan_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )
```

---

### Issue 6 — Trivy CVE database not reachable (no internet)

**Symptom**  
Trivy times out after 240 seconds trying to download `ghcr.io/aquasec/trivy-db:2`. No NAT Gateway → no internet egress from private subnets.

**Fix** — `backend/scanner/Dockerfile`  
Pre-bake the vulnerability DB during the Docker image build. Added `ENV TRIVY_CACHE_DIR` and `--download-db-only` step:
```dockerfile
ENV TRIVY_CACHE_DIR=/var/cache/trivy
RUN mkdir -p /var/cache/trivy && chmod 777 /var/cache/trivy && \
    trivy image --download-db-only --no-progress && \
    chmod -R a+rX /var/cache/trivy/db
```
Also added `--skip-db-update` to the trivy scan command in `scan.py` so it uses the baked-in DB.

---

### Issue 7 — Trivy cache not writable by non-root scanner user

**Symptom**  
`FATAL: unable to initialize cache: failed to create cache dir: mkdir /var/cache/trivy/fanal: permission denied`

**Root Cause**  
`--download-db-only` runs as `root` during build (populates `/var/cache/trivy/db/`). At runtime, the container runs as the `scanner` user, which cannot create the `fanal/` subdirectory inside `/var/cache/trivy/` because `chmod 755` was used (no write for others).

**Fix** — `backend/scanner/Dockerfile`  
Changed to `chmod 777 /var/cache/trivy` before download so the non-root user can write subdirectories at runtime:
```dockerfile
RUN mkdir -p /var/cache/trivy && chmod 777 /var/cache/trivy && \
    trivy image --download-db-only --no-progress && \
    chmod -R a+rX /var/cache/trivy/db
```

---

### Issue 8 — ECR auth required for Syft (PENDING FIX)

**Symptom**  
```
syft failed: oci-registry: failed to get image descriptor from registry:
GET https://ABC-EXAMPLE-XXXX.dkr.ecr.us-east-1.amazonaws.com/v2/.../manifests/v3:
unexpected status code 401 Unauthorized
```

**Root Cause**  
Trivy has native AWS SDK support and resolves ECR credentials from the ECS task role automatically. Syft does **not** — it uses the Docker credential chain (config.json / credential helpers). In Fargate (no Docker daemon), syft falls through to direct OCI registry access without injecting AWS credentials.

**Planned Fix** — `backend/scanner/scan.py`  
Call `ecr.get_authorization_token()` before syft runs and write credentials to `~/.docker/config.json`:
```python
def _write_ecr_docker_config() -> None:
    ecr = boto3.client("ecr", region_name=AWS_REGION)
    auth_data = ecr.get_authorization_token()["authorizationData"][0]
    config = {"auths": {auth_data["proxyEndpoint"]: {"auth": auth_data["authorizationToken"]}}}
    docker_dir = os.path.expanduser("~/.docker")
    os.makedirs(docker_dir, exist_ok=True)
    with open(os.path.join(docker_dir, "config.json"), "w") as fh:
        json.dump(config, fh)
```
Also use `registry:` prefix in syft invocation for direct OCI registry mode:
```python
["syft", f"registry:{image_name}", "-o", "cyclonedx-json"]
```

---

### Issue 9 — Syft version check fails (no internet, PENDING FIX)

**Symptom**  
`[0030] ERROR failed to fetch latest version: Get "https://toolbox-data.anchore.io/syft/releases/latest/VERSION": dial tcp ...: i/o timeout`

**Root Cause**  
Syft checks for a newer version on startup via a public URL. No internet access from private subnets.

**Planned Fix** — `backend/scanner/scan.py`  
Set `SYFT_CHECK_FOR_APP_UPDATE=false` in the subprocess environment:
```python
env = {**os.environ, "SYFT_CHECK_FOR_APP_UPDATE": "false"}
result = subprocess.run(["syft", ...], env=env, ...)
```

---

## Fargate Task SG — Final Egress Rules

| Rule | Destination | Covers |
|------|-------------|--------|
| TCP 443 | SG: `vpc-endpoints` SG | ECR API, ECR DKR, SQS, CloudWatch Logs (Interface endpoints) |
| TCP 443 | Prefix list: S3 (`pl-63a5400a`) | S3 Gateway endpoint (ECR layer downloads) |
| TCP 443 | Prefix list: DynamoDB (`pl-02cd2c6b`) | DynamoDB Gateway endpoint |

---

## IAM Additions (Live, Pending Terraform Codification)

### Fargate Task Role — `ecr-scan-access` inline policy
Added to allow Trivy to authenticate to ECR to pull the target image for scanning:
```json
{
  "Sid": "ECRScanAccess",
  "Effect": "Allow",
  "Action": [
    "ecr:GetAuthorizationToken",
    "ecr:BatchGetImage",
    "ecr:GetDownloadUrlForLayer",
    "ecr:BatchCheckLayerAvailability"
  ],
  "Resource": "*"
}
```
This is also codified in `terraform/phase2/modules/iam_phase2/main.tf` under `aws_iam_role_policy.fargate_task`.

---

## Current Scanner Image Progression

| Tag | Revision | Key Change | Outcome |
|-----|----------|------------|---------|
| `env-vars` | 10 | Env var-based scan_id (but stale build) | FAIL — old code |
| `v3` | 11 | Correct env var code + import json fix | FAIL — DynamoDB timeout |
| `v4` | 12 | Pre-baked trivy DB | FAIL — trivy cache permissions |
| `v5` | 13 | chmod 777 trivy cache | FAIL — empty trivy output (wrong returncode check) |
| `v6` | 14 | Debug logging added to run_trivy | FAIL — trivy cache fanal permissions (root) |
| `v7` | 15 | chmod 777 before db download | **PARTIAL** — Trivy ✓, Syft ✗ (ECR 401 + version check) |

**Current deployed revision**: 15 (`v7`)

---

## Next Steps (Resume Point)

Resume from scanner image **v7** (revision 15). Two fixes needed before a clean E2E run:

1. **Fix syft** — add `_write_ecr_docker_config()` call before syft and `SYFT_CHECK_FOR_APP_UPDATE=false` env var
2. **Build `v8`** — `docker build --platform linux/amd64 -t .../img-analyzer-dev-scanner:v8 .`
3. **Push + register revision 16**
4. **Run E2E** — `POST /api/v2/analyze/image` with an ECR image, verify DDB → COMPLETE
5. **Test `GET /api/v2/results/{scan_id}`** — confirm presigned S3 URLs returned
6. **Run unit tests** — `make test-backend` (76/76 expected)
7. **Commit** all untracked Phase 2 files to `phase2` branch

### Docker Hub images (future work)
Docker Hub images (`nginx:alpine`, `python:3.12-slim`) are blocked because there is no NAT Gateway and no Docker Hub VPC endpoint. Options for Phase 2 or Phase 3:
- **ECR Pull-Through Cache** for `registry-1.docker.io` — pulls via the ECR DKR VPC endpoint (cleanest, no NAT cost)
- **NAT Gateway** — adds ~$32/month per AZ, gives full internet access
