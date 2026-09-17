# IAM Access Analyzer — Setup & Usage Guide

**Project**: DocImgAnalizer  
**Created**: 2026-07-07  
**Purpose**: Identify unused permissions in the GitHub Actions role after widening
`s3:*` on Phase 2 buckets, so the policy can be locked back down to explicit actions.

---

## Background

During Phase 2 CI pipeline debugging, Terraform was hitting a long tail of S3 read
actions (`GetBucketAcl`, `GetBucketWebsite`, `GetAccelerateConfiguration`, etc.) that
are not practical to enumerate upfront. The `TerraformManageS3Phase2` statement was
widened to `s3:*` scoped to specific bucket ARNs as a temporary measure.

The resource scope (two specific bucket ARNs) is the real security boundary — not the
action list. `s3:*` on named buckets carries the same blast radius as explicit actions
on those same buckets.

IAM Access Analyzer unused access findings will identify which S3 actions were never
called, giving ground-truth data to lock the policy back down.

---

## Analyzers Created

| Name | Type | Region | Cost |
|------|------|--------|------|
| `docimganalyzer-external-access` | `ACCOUNT` | `us-east-1` | Free |
| `docimganalyzer-unused-access` | `ACCOUNT_UNUSED_ACCESS` | `us-east-1` | ~$0.20/role/month |

**Unused access window**: 5 days — any permission not called in the last 5 days is
flagged as unused.

### Create command (used 2026-07-07)

```bash
aws accessanalyzer create-analyzer \
  --analyzer-name docimganalyzer-unused-access \
  --type ACCOUNT_UNUSED_ACCESS \
  --region us-east-1
```

### Delete command (used 2026-07-17)

```bash
aws accessanalyzer delete-analyzer \
  --analyzer-name docimganalyzer-unused-access \
  --region us-east-1
```

> **2026-07-17: `docimganalyzer-unused-access` deleted as part of a cost-saving pass.**
> It was account-wide (70 IAM roles + 6 users at the time of deletion, ~$15.20/month) and
> had already served its purpose — the S3 policy lockdown work below was completed using
> its findings, so the ground-truth data needed for `TerraformManageS3Phase2` is captured
> in this doc and no longer depends on the analyzer staying active. `docimganalyzer-external-access`
> (free) remains active. Recreate on demand with the create command above if unused-access
> findings are needed again in the future.

---

## Verify Analyzers Are Active

```bash
aws accessanalyzer list-analyzers \
  --region us-east-1 \
  --output table
```

Expected output: both analyzers with status `ACTIVE`.

---

## Query Unused Permissions (run after 5+ days of pipeline activity)

```bash
aws accessanalyzer list-findings-v2 \
  --analyzer-arn $(aws accessanalyzer list-analyzers --region us-east-1 \
    --query "analyzers[?name=='docimganalyzer-unused-access'].arn" \
    --output text) \
  --region us-east-1 \
  --output json | python3 -c "
import json, sys
findings = json.load(sys.stdin).get('findings', [])
for f in findings:
    if 'github-actions' in f.get('resource', ''):
        print(f.get('resource'))
        details = f.get('findingDetails', {})
        unused = details.get('unusedPermissionDetails', {})
        actions = unused.get('actions', [])
        for a in actions:
            print(f'  UNUSED: {a}')
"
```

Actions printed as `UNUSED` were never called — safe to remove from the policy.
Actions **not listed** are the ones actually used — those go into the explicit list.

---

## How to Lock Down the Policy

After collecting findings:

1. Note every S3 action that was **not** flagged as unused — that is the exact list
   the pipeline actually calls.

2. Edit `terraform/phase2/modules/iam_phase2/main.tf`, replacing `s3:*` in
   `TerraformManageS3Phase2` with the explicit list:

```hcl
{
  Sid    = "TerraformManageS3Phase2"
  Effect = "Allow"
  Action = [
    # paste only the actions Access Analyzer did NOT flag as unused
    "s3:CreateBucket",
    "s3:GetBucketVersioning",
    # ...
  ]
  Resource = [
    "arn:aws:s3:::img-analyzer-dev-cve-reports",
    "arn:aws:s3:::img-analyzer-dev-sbom-reports",
    "arn:aws:s3:::img-analyzer-dev-cve-reports/*",
    "arn:aws:s3:::img-analyzer-dev-sbom-reports/*",
  ]
}
```

3. Apply and push:

```bash
cd terraform/phase2
terraform apply \
  -var-file=environments/dev/terraform.tfvars \
  -target=module.iam_phase2.aws_iam_role_policy.github_actions \
  -auto-approve

git add terraform/phase2/modules/iam_phase2/main.tf
git commit -m "fix(iam): lock TerraformManageS3Phase2 to exact actions per Access Analyzer"
git push origin phase2
```

---

## Validate Any Permission Change Before Pushing

Use `simulate-principal-policy` with the real resource ARNs to confirm an action
is allowed before running the pipeline:

```bash
ROLE_ARN="arn:aws:iam::ABC-EXAMPLE-XXXX:role/img-analyzer-dev-phase2-github-actions"

aws iam simulate-principal-policy \
  --policy-source-arn "$ROLE_ARN" \
  --action-names "s3:GetBucketVersioning" "s3:PutEncryptionConfiguration" \
  --resource-arns \
    "arn:aws:s3:::img-analyzer-dev-cve-reports" \
    "arn:aws:s3:::img-analyzer-dev-sbom-reports" \
  --output json | python3 -c "
import json, sys
results = json.load(sys.stdin)['EvaluationResults']
for r in results:
    print(r['EvalDecision'], r['EvalActionName'], r['EvalResourceName'])
"
```

---

## Diagnose Pipeline 403 Errors via CloudTrail

When the pipeline fails with an `UnauthorizedOperation` or `AccessDenied`, find the
exact action immediately — no guessing required:

```bash
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
```

Apply the fix immediately to AWS before pushing, so the next pipeline run starts
with the correct permissions already in place:

```bash
cd terraform/phase2
terraform apply \
  -var-file=environments/dev/terraform.tfvars \
  -target=module.iam_phase2.aws_iam_role_policy.github_actions \
  -auto-approve
```

---

## Current Policy Scope Summary

| Statement | Actions | Resource Scope |
|-----------|---------|----------------|
| `TerraformState` | Explicit S3 read/write | TF state bucket only |
| `TerraformManageS3Phase2` | `s3:*` *(temporary)* | `cve-reports` + `sbom-reports` buckets |
| `TerraformManageFrontendS3` | Explicit S3 read/write | `frontend` bucket only |
| All other statements | Explicit actions | Project-scoped ARNs |
