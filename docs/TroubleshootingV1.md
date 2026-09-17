# Troubleshooting Guide — DocImgAnalizer Phase 1

This document captures every issue encountered during the initial build and deployment of the
DocImgAnalizer project, along with the root cause and the fix applied. Use it as a reference
for future projects built on the same stack (FastAPI Lambda + React/Vite + Terraform + GitHub Actions OIDC).

---

## Local Terraform Workflow (Bootstrap / Troubleshooting)

Run these commands every time you need to apply changes locally. Always run plan before apply
to surface errors early.

```bash
cd terraform

# Dev
terraform init -reconfigure -backend-config=environments/dev/backend.hcl
terraform plan  -var-file=environments/dev/terraform.tfvars -no-color
terraform apply -var-file=environments/dev/terraform.tfvars -auto-approve

# Prod
terraform init  -reconfigure -backend-config=environments/prod/backend.hcl
terraform plan  -var-file=environments/prod/terraform.tfvars -no-color
terraform apply -var-file=environments/prod/terraform.tfvars -auto-approve
```

Use `-reconfigure` (not `-migrate-state`) when switching between environments. Each environment
has its own state file in S3. `-migrate-state` would copy one environment's state into the
other — a destructive mistake.

---

## Issue Index

| # | Area | Error Summary |
|---|------|---------------|
| 1 | Terraform / HCL | Semicolons in HCL attribute blocks |
| 2 | Terraform / S3 backend | `dynamodb_table` deprecated — use `use_lockfile` |
| 3 | Terraform / S3 backend | `use_lockfile` requires Terraform >= 1.10.0 |
| 4 | Terraform / CI version | CI Terraform version out of sync with local |
| 5 | AWS / WAFv2 | Cannot associate REGIONAL WAF with API Gateway HTTP API v2 `$default` stage |
| 6 | AWS / IAM | IAM role descriptions reject non-ASCII characters (em dash) |
| 7 | AWS / Lambda | `last_modified` in `ignore_changes` causes provider warning |
| 8 | AWS / S3 | Lifecycle rules require explicit `filter {}` block |
| 9 | AWS / API Gateway | `access_log_settings` requires `format` alongside `destination_arn` |
| 10 | AWS / CloudWatch | Dashboard metric widgets require `region` in every `properties` block |
| 11 | GitHub Actions / OIDC | Jobs using named Environments emit a different JWT subject |
| 12 | GitHub Actions / YAML | Non-ASCII characters cause `startup_failure` |
| 13 | GitHub Actions / Node | Actions compiled for Node 20 generate deprecation warnings on Node 24 runners |
| 14 | GitHub Actions / IAM | GitHub Actions role missing read permissions for Terraform state refresh |
| 15 | GitHub Actions / npm | `npm ci` fails without `package-lock.json` committed |
| 16 | Frontend / TypeScript | `import.meta.env` unresolved without `vite-env.d.ts` |
| 17 | Frontend / TypeScript | `Record<string, unknown>` values not assignable to `ReactNode` |
| 18 | Python / Ruff | Unused `import pytest` triggers F401 lint error |
| 19 | API / CORS | FastAPI behind API Gateway HTTP API v2 returns 405 on OPTIONS preflight |

---

## Detailed Issues and Fixes

---

### 1. Semicolons in HCL attribute blocks

**Symptom**

```
Error: An argument definition must end with a newline.
  on modules/monitoring/main.tf line 114
```

**Root cause**

HCL does not allow semicolons to separate attributes on the same line. Each attribute must be
on its own line.

**Fix**

```hcl
# WRONG
x = 0; y = 0; width = 8; height = 6

# CORRECT
x      = 0
y      = 0
width  = 8
height = 6
```

---

### 2. S3 backend `dynamodb_table` deprecated

**Symptom**

```
Warning: Deprecated attribute
  "dynamodb_table" is deprecated. Use use_lockfile instead.
```

**Root cause**

The `dynamodb_table` attribute in `backend.hcl` is deprecated in newer Terraform versions.
State locking is now handled natively by S3 using a lock file.

**Fix**

Replace in `environments/dev/backend.hcl` and `environments/prod/backend.hcl`:

```hcl
# BEFORE
dynamodb_table = "terraform-state-lock"

# AFTER
use_lockfile = true
```

After changing, reinitialize:

```bash
terraform init -reconfigure -backend-config=environments/<env>/backend.hcl
```

---

### 3. `use_lockfile` requires Terraform >= 1.10.0

**Symptom**

```
Error: Unsupported argument
  on environments/dev/backend.hcl line 4:
   4: use_lockfile = true
An argument named "use_lockfile" is not expected here.
```

**Root cause**

`use_lockfile` was introduced in Terraform 1.10.0. The CI pipeline was pinned to 1.9.0.

**Fix**

Update `TF_VERSION` in both workflow files to match the local Terraform version:

```yaml
env:
  TF_VERSION: '1.15.6'   # match output of: terraform version
```

Check local version with `terraform version` and always keep CI in sync.

---

### 4. CI Terraform version out of sync with local

**Symptom**

Commands that work locally fail in CI because the two versions interpret HCL or provider
behavior differently.

**Fix**

Always set `TF_VERSION` in workflow files to the exact version installed locally.
Check with `terraform version` before every project. Record it in memory/MEMORY.md.

---

### 5. WAFv2 cannot be associated with API Gateway HTTP API v2 `$default` stage

**Symptom**

```
Error: creating WAFv2 WebACL Association
WAFInvalidParameterException: Error reason: The referenced resource does not exist.
```

**Root cause**

AWS WAFv2 does not support `aws_wafv2_web_acl_association` with the `$default` stage of an
HTTP API v2. The `$` character in the stage ARN is rejected by the WAF API.

**Fix**

- Remove the `REGIONAL` WAFv2 WebACL and its association entirely.
- Remove the `waf_arn` variable from the api_gateway module.
- Protect the API with stage-level throttling and CORS restrictions instead.
- If WAF on the API is required in a future phase, place an ALB in front of Lambda and
  attach a REGIONAL WAF to the ALB.
- The CloudFront WAF (CLOUDFRONT scope) is unaffected and works normally.

Files changed: `modules/waf/main.tf`, `modules/waf/outputs.tf`,
`modules/api_gateway/main.tf`, `modules/api_gateway/variables.tf`, `main.tf`.

---

### 6. IAM role descriptions reject non-ASCII characters

**Symptom**

```
Error: creating IAM Role: ValidationError: Member must satisfy regular expression pattern:
[\u0009\u000A\u000D\u0020-\u007E\u00A1-\u00FF]+
```

**Root cause**

IAM role and policy `description` fields only accept characters in the range U+0009–U+00FF.
The em dash `—` (U+2014) is above this ceiling and is rejected.

**Fix**

Replace every em dash `—` with a regular hyphen `-` in all `description` fields on
`aws_iam_role` and `aws_iam_policy` resources.

---

### 7. Lambda `last_modified` in `ignore_changes`

**Symptom**

```
Warning: Redundant ignore_changes element
  The attribute "last_modified" is set by the provider alone and cannot be influenced.
```

**Root cause**

`last_modified` on `aws_lambda_function` is a provider-managed computed attribute with no
configurable value. Including it in `ignore_changes` is redundant and causes a warning.

**Fix**

Remove `last_modified` from the `ignore_changes` list:

```hcl
lifecycle {
  ignore_changes = [
    filename,
    source_code_hash,
  ]
}
```

---

### 8. S3 lifecycle rules require explicit `filter {}` block

**Symptom**

```
Error: Invalid Attribute Combination
  Exactly one of these attributes must be configured: filter.0.and, filter.0.object_size_*,
  filter.0.prefix, filter.0.tag
```

**Root cause**

The AWS provider requires an explicit `filter {}` block in every `rule {}` inside
`aws_s3_bucket_lifecycle_configuration`, even when the rule applies to all objects.

**Fix**

```hcl
rule {
  id     = "tiered-storage"
  status = "Enabled"

  filter {}   # required even for all-objects rules

  transition { ... }
}
```

---

### 9. API Gateway v2 `access_log_settings` requires `format`

**Symptom**

```
Error: creating API Gateway v2 Stage: BadRequestException: Exactly one of [destinationArn, format]
must be specified.
```

**Root cause**

The `access_log_settings` block in `aws_apigatewayv2_stage` requires both `destination_arn`
and `format`. Omitting `format` causes a validation error.

**Fix**

```hcl
access_log_settings {
  destination_arn = aws_cloudwatch_log_group.api_gw.arn
  format = jsonencode({
    requestId        = "$context.requestId"
    ip               = "$context.identity.sourceIp"
    requestTime      = "$context.requestTime"
    httpMethod       = "$context.httpMethod"
    routeKey         = "$context.routeKey"
    status           = "$context.status"
    responseLength   = "$context.responseLength"
    integrationError = "$context.integrationErrorMessage"
  })
}
```

---

### 10. CloudWatch dashboard metric widgets require `region`

**Symptom**

```
Error: putting CloudWatch Dashboard: InvalidParameterInput: Invalid widget definition
```

**Root cause**

Every metric widget `properties` block in `aws_cloudwatch_dashboard` must include a `region`
field. CloudWatch rejects the entire dashboard body if any widget is missing it.

**Fix**

Add a data source at the top of the module and reference it in every widget:

```hcl
data "aws_region" "current" {}

properties = {
  region  = data.aws_region.current.name   # required in every widget
  title   = "API 5xx Errors"
  ...
}
```

---

### 11. GitHub Actions OIDC — named Environments emit a different JWT subject

**Symptom**

```
Error: Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity
```

Repeats 12 times then fails. Occurs on jobs that declare `environment: development` or
`environment: production`.

**Root cause**

When a GitHub Actions job targets a named Environment, the JWT subject claim changes from:

```
repo:org/repo:ref:refs/heads/develop
```

to:

```
repo:org/repo:environment:development
```

The IAM role trust policy was only listing `ref:refs/heads/*` and `pull_request` subjects,
so AWS rejected every token issued by an environment-scoped job.

**Fix**

Add the environment subjects to the OIDC trust policy in `modules/iam/main.tf`:

```hcl
condition {
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values = [
    "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main",
    "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/develop",
    "repo:${var.github_org}/${var.github_repo}:pull_request",
    "repo:${var.github_org}/${var.github_repo}:environment:development",
    "repo:${var.github_org}/${var.github_repo}:environment:production",
  ]
}
```

Then run `terraform apply` locally to update the role before the next CI run.

---

### 12. Non-ASCII characters in GitHub Actions YAML cause `startup_failure`

**Symptom**

```
This run likely failed because of a bad workflow file.
Error: startup_failure
```

No further details are shown in the Actions UI. The job never starts.

**Root cause**

GitHub's YAML parser rejects workflow files containing non-ASCII characters such as
`•`, `→`, `─`, `✓`, `—`, `←`, `⚠`, `❌`. These often appear in comments, step names,
or echo statements copied from documentation or terminals.

**Fix**

Scan for non-ASCII characters before committing:

```bash
python3 -c "
import sys
with open('.github/workflows/deploy.yml') as f:
    for i, line in enumerate(f, 1):
        bad = [(j, c) for j, c in enumerate(line) if ord(c) > 127]
        if bad:
            print(f'Line {i}: {bad}')
"
```

Replace all non-ASCII characters with plain ASCII equivalents:
- `—` (em dash) -> `-`
- `•` (bullet) -> `*`
- `→` (arrow) -> `->`
- `✓` (check) -> `[OK]`
- `⚠` (warning) -> `[WARN]`
- `❌` (cross) -> `[FAIL]`

---

### 13. GitHub Actions Node 20 deprecation warning

**Symptom**

```
Node.js 20 is being deprecated on GitHub Actions runners. This workflow is running with
Node 24 by default.
```

**Root cause**

Older action versions were compiled for Node 20. GitHub Actions runners now default to Node 24.

**Fix**

Use the latest action versions that target Node 24:

| Action | Old | New |
|--------|-----|-----|
| `actions/checkout` | `@v4` | `@v7` |
| `actions/setup-python` | `@v5` | `@v6` |
| `actions/setup-node` | `@v4` | `@v6` |
| `actions/github-script` | `@v7` | `@v9` |
| `aws-actions/configure-aws-credentials` | `@v4` | `@v5` |

---

### 14. GitHub Actions role missing read permissions for Terraform state refresh

**Symptom**

```
Error: listing tags for CloudWatch Logs Log Group: AccessDeniedException:
  not authorized to perform: logs:ListTagsForResource

Error: finding IAM OIDC Provider: AccessDenied:
  not authorized to perform: iam:ListOpenIDConnectProviders

Error: listing tags for CloudWatch Metric Alarm: AccessDenied:
  not authorized to perform: cloudwatch:ListTagsForResource

Error: reading S3 Bucket replication configuration: AccessDenied:
  not authorized to perform: s3:GetReplicationConfiguration
```

**Root cause**

Terraform's AWS provider calls several read/tag-listing APIs during state refresh (at the
start of both `plan` and `apply`). These were not included in the GitHub Actions IAM role policy.

**Fix**

Add to the `CloudWatchManage` policy statement:
- `logs:ListTagsForResource`
- `cloudwatch:ListTagsForResource`

Add to the `IAMManage` policy statement:
- `iam:ListOpenIDConnectProviders`
- Add `arn:aws:iam::*:oidc-provider/*` to its resource list

Add to the `S3Deploy` policy statement:
- `s3:GetReplicationConfiguration`

Add to the `LambdaDeploy` policy statement:
- `lambda:GetFunctionCodeSigningConfig`
- `lambda:GetFunctionConcurrency`
- `lambda:GetFunctionUrlConfig`
- `lambda:GetRuntimeManagementConfig`

**Prevention**

When adding any new AWS resource to Terraform, also grant its read actions (`List*`, `Get*`,
`Describe*`, `ListTagsForResource`) to the GitHub Actions role at the same time.

Run `terraform plan` locally as the GitHub Actions role (or check the plan output in CI)
before merging to catch missing permissions before `apply` runs.

---

### 15. `npm ci` fails without `package-lock.json` committed

**Symptom**

```
npm error The `npm ci` command can only install with an existing package-lock.json
```

**Root cause**

`npm ci` (used in CI for reproducible installs) requires `package-lock.json` to be present
and committed. Running only `npm install` locally without committing the lockfile causes CI
to fail.

**Fix**

```bash
cd frontend
npm install          # generates package-lock.json
git add package-lock.json
git commit -m "chore: add frontend package-lock.json for npm ci"
```

The lockfile must be committed and kept up to date whenever `package.json` changes.

---

### 16. `import.meta.env` unresolved in TypeScript

**Symptom**

```
error TS2339: Property 'env' does not exist on type 'ImportMeta'.
  src/api/client.ts(5,30)
```

**Root cause**

Vite augments the global `ImportMeta` interface to add `.env`, but this augmentation is
only applied when the Vite client type declarations are referenced. Without the reference,
TypeScript's default `ImportMeta` type has no `env` property.

**Fix**

Create `frontend/src/vite-env.d.ts`:

```typescript
/// <reference types="vite/client" />
```

This single line pulls in Vite's type augmentations, including `ImportMeta.env`.

---

### 17. `Record<string, unknown>` values not assignable to `ReactNode`

**Symptom**

```
error TS2322: Type 'unknown' is not assignable to type 'ReactNode'.
  src/pages/ResultsPage.tsx(143,67)
```

**Root cause**

API response metadata is typed as `Record<string, unknown>`. When individual values are
rendered directly in JSX or used as JSX conditionals, TypeScript rejects `unknown` because
it cannot guarantee the value is renderable.

**Fix**

Wrap string values with `String()` and use `!!` for boolean coercion in conditionals:

```tsx
// BEFORE
{report.metadata.namespace}/{report.metadata.name}:{report.metadata.tag}
{report.metadata.digest && ( ... )}

// AFTER
{String(report.metadata.namespace)}/{String(report.metadata.name)}:{String(report.metadata.tag)}
{!!report.metadata.digest && ( ... )}
```

---

### 18. Unused `import pytest` triggers Ruff F401

**Symptom**

```
backend/tests/test_dockerfile_analyzer.py:1:8: F401 `pytest` imported but unused
backend/tests/test_routers.py:1:8: F401 `pytest` imported but unused
```

**Root cause**

pytest discovers and runs tests automatically — it does not need to be explicitly imported
in test files unless you are using pytest-specific fixtures or markers directly.

**Fix**

Remove `import pytest` from any test file that does not use `pytest.mark`, `pytest.raises`,
`pytest.fixture`, or similar pytest APIs directly.

---

### 19. FastAPI behind API Gateway HTTP API v2 returns 405 on OPTIONS preflight

**Symptom**

Browser UI shows "Failed to fetch" when submitting a form. curl requests to the same
endpoint succeed. CORS preflight returns HTTP 405:

```bash
curl -i -X OPTIONS https://api.example.com/api/v1/analyze/dockerfile \
  -H "Origin: https://frontend.example.com" \
  -H "Access-Control-Request-Method: POST"

# HTTP/2 405
# access-control-allow-origin: https://frontend.example.com  <- headers present
# {"detail":"Method Not Allowed"}                            <- but status is wrong
```

**Root cause**

API Gateway HTTP API v2 `cors_configuration` adds the correct CORS headers to responses
but still forwards OPTIONS preflight requests to Lambda via the `$default` catch-all route.
FastAPI has no OPTIONS handler so it returns 405. The browser requires a 2xx on preflight
— a 4xx causes it to block the actual request entirely, producing "Failed to fetch".

**Fix**

Add FastAPI's `CORSMiddleware` to `app/main.py`. It intercepts OPTIONS before the router
and returns 200 with the correct headers:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "https://imgapp.craftingnewtech.com")],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)
```

Read the allowed origin from a Lambda environment variable (already set by Terraform)
rather than hardcoding it.

**Verify the fix**

```bash
curl -i -X OPTIONS https://api.example.com/api/v1/analyze/dockerfile \
  -H "Origin: https://frontend.example.com" \
  -H "Access-Control-Request-Method: POST"
# Expected: HTTP/2 200 with access-control-allow-origin header
```

---

## Key Principle: Plan Before Apply

Always run `terraform plan` before `terraform apply`, both locally and in CI:

- State refresh errors (IAM permissions, API calls) appear at the plan stage — fixing them
  before apply avoids a partial apply state.
- The plan output shows exactly what will change, preventing surprises.
- In the deploy workflow, a `Terraform Plan` step runs before `Terraform Apply` and saves
  a plan file (`-out=tfplan`). Apply then executes only that exact plan.

The PR workflow (`pr.yml`) also runs plan on every pull request. Use pull requests for all
changes to `develop` or `main` rather than pushing directly — this ensures the plan check
runs before any deployment is triggered.
