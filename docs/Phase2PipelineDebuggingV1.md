# Phase 2 Pipeline Debugging Log — V1

**Date:** 2026-07-06  
**Branch:** `phase2`  
**Pipeline:** `.github/workflows/phase2-deploy.yml`  
**Final status:** All steps green — run `28825616639` succeeded in 1m55s

---

## Overview

Getting the Phase 2 CI/CD pipeline to a clean pass required resolving three categories of issues:

1. **GitHub Actions IAM role bootstrap catch-22** — the Phase 2 role was too restrictive to run `terraform apply`, but Terraform had to run to grant itself more permissions.
2. **Pipeline script bugs** — copy-into-self, ECR immutable-tag collision, wrong Terraform output.
3. **Missing ECS lifecycle management** — `:latest` tag cannot be reused when ECR tags are immutable.

---

## Fix Log

| # | Step that failed | Root Cause | Fix Applied |
|---|-----------------|------------|-------------|
| 1 | `terraform apply (dev)` — `cognito-idp:DescribeUserPool`, `ecr:DescribeRepositories`, `logs:DescribeLogGroups`, `ecs:DescribeClusters`, `iam:GetRole`, `kms:DescribeKey`, `s3:GetBucketVersioning` | Phase 2 GitHub Actions role only had 4 deployment statements: `TerraformState`, `LambdaV2Deploy`, `ECRPush`, `ECSRegisterTask`. Terraform refresh reads every managed resource and hit AccessDenied. | Added 15 `TerraformManage*` statements for every Phase 2 service (Cognito, ECR, ECS, VPC/EC2, SQS, KMS, IAM, CloudWatch Logs, DynamoDB, Lambda, Pipes, CloudWatch, SNS, S3, API Gateway). Applied locally via `-target=module.iam_phase2.aws_iam_role_policy.github_actions` to break the bootstrap cycle. |
| 2 | `terraform apply (dev)` — `cognito-idp:DescribeUserPoolDomain` | `TerraformManageCognito` scoped resource to `arn:aws:cognito-idp:...:userpool/*`. `DescribeUserPoolDomain` requires `Resource: *` because domains are not user pool ARNs. | Changed Cognito statement to `Resource = "*"`. |
| 3 | `terraform apply (dev)` — `apigateway:GET on .../authorizers/...` | `apigateway:*` was completely absent from the Phase 2 role (Phase 1 role had it; Phase 2 role was written from scratch). | Added `TerraformManageAPIGateway = ["apigateway:*"]` on `Resource = "*"`. |
| 4 | `terraform apply (dev)` — `s3:GetBucketCORS`, `s3:GetBucketReplication` | Individual S3 actions enumerated — Terraform provider calls ~15 different `Get*` actions during bucket refresh. Chasing them one-by-one is unsustainable. | Changed `TerraformManageS3Phase2` from an explicit action list to `s3:*` scoped to the Phase 2 bucket ARNs. |
| 5 | `terraform apply (dev)` — `lambda:GetFunctionCodeSigningConfig` | Lambda action list missed `GetFunctionCodeSigningConfig`, `GetFunctionUrlConfig`, `GetRuntimeManagementConfig` (all called by TF provider during refresh). | Changed `TerraformManageLambda` from an explicit action list to `lambda:*` scoped to `img-analyzer-dev-*` function ARN prefix. |
| 6 | `Build Lambda v2 package` — `cp: cannot copy a directory, 'backend/v2', into itself` | Workflow ran `pip install --target backend/v2/package` then `cp -r backend/v2 backend/v2/package/`. `package/` is a subdirectory of `v2/`, so copying the parent into the child triggers the OS error. | Changed build to use `BUILD=$(mktemp -d)`, install deps there, then `cp -r backend/v2/. "$BUILD/"` and `cp -r backend/app "$BUILD/"`. |
| 7 | `Build + push scanner` — `tag invalid: The image tag 'latest' already exists … cannot be overwritten because the tag is immutable` | ECR repository was set to `IMMUTABLE` (a Trivy IaC security finding fixed in the local checks). Once `:latest` existed, no subsequent push could overwrite it. | Removed `docker tag … :latest` and `docker push … :latest` lines. Pipeline now only pushes the `${{ github.sha }}` tag. |
| 8 | `Build + push scanner` — ECS task definition hardcoded `:latest` | `container_definitions` had `image = "${var.ecr_repository_url}:latest"`. With immutable ECR tags, this would reset the task definition to a non-pushable tag on every `terraform apply`. | Added `variable "scanner_image_tag" { default = "latest" }` to ECS module, added `lifecycle { ignore_changes = [container_definitions] }` so Terraform stops reconciling the image tag. Added a post-push step in the pipeline to register a new task definition revision with the SHA tag. |
| 9 | `Sync frontend to S3` — `aws: [ERROR]: An error occurred (ParamValidation): Unknown options: exited,with,code,1.,img-analyzer-dev-frontend/` | Workflow did `BUCKET=$(cd terraform/phase2 && terraform output -raw frontend_bucket 2>/dev/null \|\| echo "img-analyzer-dev-frontend")`. `frontend_bucket` is not a Phase 2 output — it belongs to Phase 1 state. `terraform output` printed its error message to **stdout** (not stderr), so the subshell captured `"exited with code 1.\nimg-analyzer-dev-frontend"` as the bucket name. | Changed to read the bucket from Phase 1 state: `BUCKET=$(cd terraform/phase1 && terraform init ... && terraform output -raw frontend_bucket 2>/dev/null) \|\| BUCKET="img-analyzer-dev-frontend"` — same pattern used by the CloudFront invalidation step in the same workflow. |

---

## Bootstrap Catch-22 — Pattern to Remember

The Phase 2 IAM role is **self-managed by Terraform** (it lives inside `module.iam_phase2`). Any time the role's permissions are insufficient for Terraform to run, the pipeline cannot self-heal — it can't apply the fix because it can't authenticate to apply anything.

**Resolution protocol:**
1. Edit the IAM policy in `terraform/phase2/modules/iam_phase2/main.tf`.
2. Apply **locally** with `-target=module.iam_phase2.aws_iam_role_policy.github_actions` using admin credentials.
3. Commit and push — the pipeline then has enough permission to handle all future applies autonomously.

This is a one-time bootstrapping concern. Future permission additions follow the same targeted-apply pattern.

---

## IAM Role — Final Permission Summary

`img-analyzer-dev-phase2-github-actions` inline policy statements after all fixes:

| Statement Sid | Scope | Purpose |
|--------------|-------|---------|
| `TerraformState` | S3 state bucket | Read/write Terraform state |
| `LambdaV2Deploy` | `img-analyzer-dev-api-v2` | Update Lambda function code |
| `ECRPush` | `img-analyzer-dev-scanner` | Push scanner images |
| `ECSRegisterTask` | `*` | Register new task definition revisions |
| `TerraformManageCognito` | `*` | Manage Cognito User Pool and domain |
| `TerraformManageAPIGateway` | `*` | Manage API Gateway routes, authorizers |
| `TerraformManageECR` | `*` | Describe/create/delete ECR repos |
| `TerraformManageECS` | `*` | Manage ECS cluster and services |
| `TerraformManageVPC` | `*` | Manage VPC, subnets, SGs, endpoints |
| `TerraformManageSQS` | `img-analyzer-dev-*` queues | Manage SQS queues and DLQ |
| `TerraformManageKMS` | `*` | Create/manage Phase 2 KMS CMK |
| `TerraformManageIAM` | `*` | Manage Phase 2 IAM roles and policies |
| `TerraformManageLogs` | `*` | Create/manage CloudWatch Log Groups |
| `TerraformManageS3Phase2` | `img-analyzer-dev-cve-reports`, `img-analyzer-dev-sbom-reports` | Full S3 management on Phase 2 buckets |
| `TerraformManageFrontendS3` | `img-analyzer-dev-frontend` | Read/write frontend bucket |
| `TerraformManageDynamoDB` | `img-analyzer-dev-*` tables | Manage Phase 2 DynamoDB table |
| `TerraformManageLambda` | `img-analyzer-dev-*` functions | Full Lambda lifecycle |
| `TerraformManagePipes` | `img-analyzer-dev-*` pipes | Manage EventBridge Pipes |
| `TerraformManageCloudWatch` | `*` | Manage dashboards and alarms |
| `TerraformManageSNS` | `img-analyzer-dev-*` topics | Manage SNS topics for alarms |
| `CloudFrontInvalidation` | `*` | Invalidate CloudFront cache post-deploy |

---

## ECS Image Tagging Strategy (Immutable ECR)

With `image_tag_mutability = "IMMUTABLE"` (required by Trivy IaC HIGH finding), each image push gets a unique SHA tag. The pipeline manages the ECS task definition update:

```bash
# After docker push $ECR_URL:$SHA ...
FAMILY="img-analyzer-dev-scanner"
CURRENT=$(aws ecs describe-task-definition --task-definition "$FAMILY" --query taskDefinition --output json)
NEW_DEF=$(echo "$CURRENT" | jq --arg img "$ECR_URL:$SHA" \
  '.containerDefinitions[0].image = $img | del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.placementConstraints,.compatibilities,.registeredAt,.registeredBy)')
aws ecs register-task-definition --cli-input-json "$NEW_DEF"
```

The `aws_ecs_task_definition` Terraform resource has `lifecycle { ignore_changes = [container_definitions] }` so `terraform apply` does not reset the image tag back to the initial value.

---

## Commits in This Session (2026-07-06)

| SHA | Message |
|-----|---------|
| `a472d8f` | `fix(iam-phase2): add Terraform management permissions to GitHub Actions role` |
| `c0b934d` | `fix(iam-phase2): add missing APIGateway, Cognito domain, and S3 CORS permissions` |
| `7c83b80` | `fix(iam-phase2): use s3:* for Phase 2 buckets to cover all Terraform provider read calls` |
| `5e4a968` | `fix(iam-phase2): use lambda:* for Phase 2 functions to cover all provider read calls` |
| `6a9e63c` | `fix(pipeline): fix Lambda v2 package build — use temp dir to avoid cp-into-self` |
| `33ba7e6` | `fix(pipeline): fix ECR immutable-tag and ECS task def update` |
| `1094cb5` | `fix(pipeline): fix frontend S3 sync — get bucket name from Phase 1 TF output` |

---

## Session 2 — Post-Merge IAM Refinement (2026-07-07)

After the first clean pipeline run, subsequent runs surfaced additional missing EC2 and S3
permissions. The root cause in each case was the same: the Terraform AWS provider calls a
broader set of read APIs than what is explicitly configured in `.tf` files — `terraform
refresh` reads every managed resource, hitting APIs not obvious from the resource definitions.

### Fix Log (Session 2)

| # | Failing Operation | Root Cause | Fix Applied | Commit |
|---|-------------------|-----------|------------|--------|
| 10 | `ec2:DescribeManagedPrefixLists` 403 | Terraform VPC endpoint module uses `aws_ec2_managed_prefix_list` data source to look up the S3 prefix list by name — action was absent from `TerraformManageVPC`. | Added `ec2:DescribeManagedPrefixLists` to `TerraformManageVPC`. | `05eb632` |
| 11 | `ec2:GetManagedPrefixListEntries` 403 | Separate from `DescribeManagedPrefixLists` — `Describe` finds the prefix list by ID; `GetEntries` reads the CIDR block contents. Both are required. | Added `ec2:GetManagedPrefixListEntries` to `TerraformManageVPC`. | `971901f` |
| 12 | `s3:GetBucketAcl` 403 | AWS provider 5.x reads bucket ACL during every S3 resource refresh, even when ACLs are not managed by Terraform. | Added `s3:GetBucketAcl` to `TerraformManageS3Phase2`. | `971901f` |
| 13 | `s3:GetBucketWebsite` 403 | Provider reads website configuration on every refresh even when `aws_s3_bucket_website_configuration` is not present. | Added `s3:GetBucketWebsite` to `TerraformManageS3Phase2`. | `6b42ed9` |
| 14 | `s3:GetAccelerateConfiguration` 403 | IAM action name differs from the API call name — the AWS IAM service drops "Bucket" from the verb. API: `GetBucketAccelerateConfiguration` → IAM: `s3:GetAccelerateConfiguration`. | Added `s3:GetAccelerateConfiguration` to `TerraformManageS3Phase2`. | `cbb351a` |
| 15 | Further S3 read actions (tail) | Enumerating individual S3 `Get*` actions one-by-one proved unsustainable — the provider calls ~15 different read actions. The real security boundary is the resource ARN, not the action list. | Widened `TerraformManageS3Phase2` back to `s3:*` scoped to the two Phase 2 bucket ARNs (`cve-reports`, `sbom-reports`). IAM Access Analyzer (unused-access, 5-day window) created to identify actual used actions for future lock-down. | `a025870` |
| 16 | `botocore.exceptions.NoRegionError` — test collection fails in CI | `ecs_launcher.py` called `boto3.client("ecs")` at module import time. CI test runner has no `AWS_DEFAULT_REGION` set, so botocore raises `NoRegionError` before a single test runs. | Replaced module-level `_ecs = boto3.client("ecs")` with a lazy `_client()` getter that initialises the client on first call with `region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")`. | `c77f10d` |

### IAM Access Analyzer

Two analyzers created in `us-east-1` to support the S3 action lock-down:

| Analyzer | Type | Cost |
|----------|------|------|
| `docimganalyzer-external-access` | `ACCOUNT` | Free |
| `docimganalyzer-unused-access` | `ACCOUNT_UNUSED_ACCESS` | ~$0.20/role/month (prorated) |

**Unused access window**: 5 days. After 2026-07-12, query findings, replace `s3:*` with
explicit actions, delete `docimganalyzer-unused-access`. Keep `external-access` permanently.
See `docs/IAMAccessAnalyzerGuide.md` for the full lock-down procedure.

### Diagnostic Commands (for future 403 errors)

```bash
# Find the exact failing API call from CloudTrail (last 24 h)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=GitHubActions \
  --start-time "$(date -u -v-1d '+%Y-%m-%dT%H:%M:%SZ')" \
  --max-results 50 \
  --output json | python3 -c "
import json, sys
events = json.load(sys.stdin)['Events']
for e in events:
    detail = json.loads(e.get('CloudTrailEvent', '{}'))
    err = detail.get('errorCode', '')
    if 'Unauthorized' in err or 'Denied' in err:
        print(e['EventTime'], e['EventSource'], e['EventName'])
        print(' ', detail.get('errorMessage', '')[:100])
"

# Apply IAM fix immediately before next pipeline run
cd terraform/phase2
terraform apply \
  -var-file=environments/dev/terraform.tfvars \
  -target=module.iam_phase2.aws_iam_role_policy.github_actions \
  -auto-approve
```

### Final Outcome (Session 2)

- Pipeline green — all steps passing as of run `28825626XXX`
- E2E smoke test passed: health check → Cognito auth → image scan → COMPLETE
  - CVEs: 2 CRITICAL, 12 HIGH, 61 MEDIUM, 65 LOW
  - Presigned `report_url` + `sbom_url` returned
- `phase2` merged → `develop` at `94f37d4` (180 files, 14,151 insertions)
- `docs/IAMAccessAnalyzerGuide.md` committed at `34329ae`

---

## Session 3 — Terraform State Drift + KMS Permissions (2026-07-07)

### Issue 17 — Terraform State Drift: Prior Targeted Applies Never Updated Live AWS

**Symptom**

Pipeline failed again with the same errors that had already been "fixed":

```
Error: reading S3 Bucket (img-analyzer-dev-cve-reports) ACL: GetBucketAcl 403
Error: reading S3 Bucket (img-analyzer-dev-sbom-reports) ACL: GetBucketAcl 403
Error: reading EC2 Managed Prefix List Entries: GetManagedPrefixListEntries 403 (x2)
```

**Root Cause**

All prior targeted applies (`-target=module.iam_phase2.aws_iam_role_policy.github_actions`)
had reported **"0 changes"** — Terraform state already recorded the policy as up-to-date,
so Terraform skipped writing to AWS. The live IAM role in AWS was still at an older version
of the policy that predated the `s3:*` widening and the `ec2:GetManagedPrefixListEntries`
addition.

This is a **Terraform state drift in reverse**: the `.tf` source and the state file agreed
with each other, but the live AWS resource diverged — likely because an earlier full apply
wrote an intermediate version of the policy to state, but a subsequent AWS-level update
(from a different targeted apply attempt) never made it to the remote state.

**Confirmed via AWS CLI**:
```bash
aws iam get-role-policy \
  --role-name img-analyzer-dev-phase2-github-actions \
  --policy-name github-actions-phase2-policy
# TerraformManageS3Phase2 showed 23 explicit actions (not s3:*)
# TerraformManageVPC was missing ec2:GetManagedPrefixListEntries
```

**Fix**

Used `terraform apply -replace` to force Terraform to destroy and recreate the resource
regardless of what the state says:

```bash
cd terraform/phase2
terraform apply \
  -var-file=environments/dev/terraform.tfvars \
  -replace=module.iam_phase2.aws_iam_role_policy.github_actions \
  -target=module.iam_phase2.aws_iam_role_policy.github_actions \
  -auto-approve
```

Plan showed exactly the two expected diffs:
- `ec2:GetManagedPrefixListEntries` added to `TerraformManageVPC`
- `TerraformManageS3Phase2`: 23 explicit actions → `s3:*`

Result: 1 destroyed, 1 created. Pipeline passed on next run.

**Pattern to Remember**

When a targeted apply reports "0 changes" but the pipeline keeps failing on the same
permission, the state and live AWS have drifted. Use `-replace` to force reconciliation
instead of `-target` alone. Always verify with `aws iam get-role-policy` before and after.

---

### Issue 18 — `kms:Decrypt` / `kms:GenerateDataKey` Missing from GitHub Actions Role

**Symptom**

Pipeline completed successfully but the `aws lambda update-function-code` step returned
an `Environment.Error` in the JSON response:

```json
"Environment": {
  "Error": {
    "ErrorCode": "AccessDeniedException",
    "Message": "Lambda was unable to decrypt your environment variables because the KMS
    access was denied. User: assumed-role/img-analyzer-dev-phase2-github-actions/GitHubActions
    is not authorized to perform: kms:Decrypt on resource:
    arn:aws:kms:us-east-1:ABC-EXAMPLE-XXXX:key/ABC-EXAMPLE-XXXX"
  }
}
```

**Root Cause**

When `UpdateFunctionCode` is called, AWS Lambda internally needs to decrypt the existing
KMS-encrypted environment variables using the **caller's** identity (the GitHub Actions role),
not the Lambda execution role. `TerraformManageKMS` had management actions only
(`CreateKey`, `PutKeyPolicy`, etc.) but was missing `kms:Decrypt` and `kms:GenerateDataKey`.

The pipeline step still returned HTTP 200 (code was deployed successfully), so the job
didn't fail — but the error appeared in the output and the Lambda function log a transient
decryption error on startup.

**Fix**

Added two actions to `TerraformManageKMS` in `terraform/phase2/modules/iam_phase2/main.tf`:

```hcl
"kms:Decrypt", "kms:GenerateDataKey"
```

Applied via `-replace` targeted apply (same pattern as Issue 17), then committed at `b8df924`.

**Result**: Pipeline ran clean — `Environment.Error` field gone from `update-function-code`
response.

### Commits in This Session (2026-07-07)

| SHA | Message |
|-----|---------|
| `34329ae` | `docs: add IAM Access Analyzer setup and usage guide` |
| `c77f10d` | `fix(tests): defer boto3 ECS client init to avoid NoRegionError at import time` |
| `679e23b` | `docs: update Phase 2 debugging log and status report to COMPLETE` |
| `b8df924` | `fix(iam): add kms:Decrypt and kms:GenerateDataKey to GitHub Actions role` |
