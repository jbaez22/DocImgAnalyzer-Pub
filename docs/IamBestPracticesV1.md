# IAM Least Privilege — Best Practices for GitHub Actions OIDC Roles

## Context

This document captures the IAM design principles and best practices identified during Phase 1
of the DocImgAnalizer project. It applies to any project using GitHub Actions OIDC with
Terraform for infrastructure management and automated deployments to AWS.

---

## The Problem with a Single GitHub Actions Role

A common starting point (including Phase 1 of this project) is one role that does everything:

- Runs `terraform plan` on pull requests
- Runs `terraform apply` on merge to develop/main
- Deploys Lambda code, syncs S3, invalidates CloudFront

This violates least privilege. All three jobs have very different risk profiles:

| Job | Risk Level | What It Actually Needs |
|-----|-----------|------------------------|
| `terraform plan` (PR validation) | Low — read only | State access + read APIs |
| `terraform apply` (deploy) | High — creates/deletes infra, modifies IAM | Broad write access |
| App deploy (Lambda + S3 + CloudFront) | Medium — pushes code only | 3-5 specific actions |

A single role that can do all three means:
- A compromised PR can trigger infra destruction
- A buggy deploy step runs with IAM write access it does not need
- A leaked token gives an attacker full infrastructure control

---

## The Right Architecture: Three Roles

```
pr.yml
  └── github-actions-plan role    (read-only + state read)

deploy.yml
  ├── github-actions-apply role   (terraform apply — infra write)
  └── github-actions-deploy role  (lambda + s3 + cloudfront only)
```

### Role 1 — `github-actions-plan`

**Trusted by:** `pull_request` OIDC subject only

**Permissions:**
- S3 state bucket read (`s3:GetObject`, `s3:ListBucket`)
- All `Describe*`, `Get*`, `List*` read APIs across services used by Terraform
- No write access to anything

**Purpose:** Safe for PRs. Even if a malicious PR triggers a plan, no resources can be
created or modified.

---

### Role 2 — `github-actions-apply`

**Trusted by:** `environment:development` and `environment:production` OIDC subjects only

**Permissions:**
- Everything in the plan role, plus
- Full infra write for managed services (scoped to `project-env-*` ARNs where possible)
- IAM role and policy management (required for Terraform to manage roles)
- S3, Lambda, CloudFront, DynamoDB, KMS, ACM, Route53, API Gateway, CloudWatch, SNS management

**Purpose:** Applies infrastructure changes. Scoped to named GitHub Environments so it only
activates on approved deployments, never on PRs.

---

### Role 3 — `github-actions-deploy`

**Trusted by:** `environment:development` and `environment:production` OIDC subjects only

**Permissions (narrow and explicit):**

```hcl
# Lambda — code update only, no config or policy changes
"lambda:UpdateFunctionCode"
"lambda:PublishVersion"
"lambda:UpdateAlias"
"lambda:GetFunction"
"lambda:GetAlias"
"lambda:GetFunctionConfiguration"
"lambda:WaitForFunctionUpdated"

# S3 — frontend bucket only, no bucket configuration
"s3:PutObject"
"s3:DeleteObject"
"s3:ListBucket"
# Resource: arn:aws:s3:::project-env-frontend and ./*

# CloudFront — invalidation only, no distribution changes
"cloudfront:CreateInvalidation"
# Resource: specific distribution ARN only
```

**Purpose:** Deploys application code after infrastructure is confirmed good. Cannot touch
IAM, cannot create or delete resources, cannot modify infrastructure configuration.

---

## How to Generate Policies Correctly: Use `iamlive`

Never write IAM policies manually from first principles. The Terraform AWS provider makes
dozens of implicit API calls during state refresh that are not documented per-resource.
Writing policies manually leads to iterative CI failures as missing permissions are discovered
one at a time.

**`iamlive`** is a local proxy that intercepts every AWS API call and generates a minimal
IAM policy from actual usage.

### One-time setup

```bash
brew install iamlive
```

### Capture workflow

```bash
# Terminal 1 — start iamlive in capture mode
iamlive --mode proxy --output-file iam-policy-generated.json

# Terminal 2 — run terraform through the proxy with admin credentials
export HTTP_PROXY=http://127.0.0.1:10080
export HTTPS_PROXY=http://127.0.0.1:10080

cd terraform
terraform init  -reconfigure -backend-config=environments/dev/backend.hcl
terraform plan  -var-file=environments/dev/terraform.tfvars -no-color
terraform apply -var-file=environments/dev/terraform.tfvars -auto-approve
```

Stop `iamlive` after apply completes. `iam-policy-generated.json` contains every API call
made — this becomes the basis for the apply role policy. No guessing, no iterative
discovery in CI.

### Alternative: CloudTrail + IAM Access Analyzer (AWS-native, no extra tooling)

1. Run `terraform apply` once with admin credentials (CloudTrail must be enabled)
2. AWS Console → IAM → Access Analyzer → **Generate policy**
3. Select the CloudTrail trail, time window, and the IAM principal used during apply
4. Download the generated policy

Requires no additional tooling but needs 15-30 minutes for CloudTrail propagation.

---

## Add Permission Boundaries as a Safety Net

A **permission boundary** is an IAM policy attached to a role that acts as an absolute
ceiling on what the role can ever do — even if the inline policy accidentally grants more.
It is evaluated alongside the identity policy; both must allow an action for it to succeed.

```hcl
resource "aws_iam_policy" "github_actions_boundary" {
  name        = "${var.project_name}-github-actions-boundary"
  description = "Permission boundary - caps GitHub Actions roles, blocks account-level destructive actions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyDangerousActions"
        Effect = "Deny"
        Action = [
          "iam:CreateUser",
          "iam:DeleteUser",
          "iam:AttachUserPolicy",
          "iam:CreateAccessKey",
          "iam:CreateLoginProfile",
          "organizations:*",
          "account:*",
          "billing:*",
          "aws-portal:*",
        ]
        Resource = "*"
      },
      {
        Sid      = "AllowEverythingElse"
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "github_actions_apply" {
  name                 = "${var.project_name}-${var.environment}-github-actions-apply"
  permissions_boundary = aws_iam_policy.github_actions_boundary.arn
  assume_role_policy   = data.aws_iam_policy_document.github_actions_apply_assume.json
}
```

The boundary denies user creation, access key generation, and billing actions. Even if the
inline policy is misconfigured or an attacker finds a path to escalate, these actions remain
blocked at the boundary level.

---

## OIDC Subject Scoping

Each role trusts only the OIDC subjects it needs. Never give a plan-only role a subject
that can trigger on a deploy event.

```hcl
# Plan role — PR events only
values = [
  "repo:${var.github_org}/${var.github_repo}:pull_request",
]

# Apply and Deploy roles — named Environment events only
values = [
  "repo:${var.github_org}/${var.github_repo}:environment:development",
  "repo:${var.github_org}/${var.github_repo}:environment:production",
]
```

Named GitHub Environments can have required reviewers and deployment protection rules,
which means the `environment:production` subject only appears after an authorized human
has approved the deployment.

---

## Best Practices Summary

| Practice | Reason |
|----------|--------|
| Three roles (plan / apply / deploy) | Blast radius containment — a compromised deploy step cannot alter infrastructure |
| Generate policies with `iamlive` | Eliminates manual guessing and iterative CI failures |
| Permission boundaries on all roles | Hard ceiling on privileges even if policies drift |
| Environment-scoped OIDC subjects | Plan role cannot trigger apply; deploy requires Environment approval |
| Resource-level ARN scoping | Policies scoped to `project-env-*` ARNs, not `*`, where possible |
| Regular Access Analyzer reviews | Quarterly review of unused permissions via IAM Access Analyzer findings |
| No static AWS access keys anywhere | OIDC only — zero long-lived credentials |

---

## Implementation Plan for This Project

### Phase 1 (current) — Single role, pipeline stabilization

Get the CI/CD pipeline green with the current single role. Use `iamlive` to capture the
complete permission set and replace the manually-built policy.

### Phase 2 — Role split

Refactor `modules/iam/main.tf` to produce three roles:
- `github-actions-plan` (replace current role in `pr.yml`)
- `github-actions-apply` (Terraform apply steps in `deploy.yml`)
- `github-actions-deploy` (Lambda/S3/CloudFront steps in `deploy.yml`)

Update both workflow files to assume the correct role per step using
`aws-actions/configure-aws-credentials` with a different `role-to-assume` per job section.

Add permission boundaries to all three roles.

### Phase 3 — Ongoing

- Schedule quarterly IAM Access Analyzer reviews
- Run `iamlive` again whenever new services or resources are added to Terraform
- Tighten resource ARN scoping as stable patterns emerge

---

## References

- [iamlive — GitHub](https://github.com/iann0036/iamlive)
- [IAM Access Analyzer — Generate policy from CloudTrail](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-generation.html)
- [AWS Permission Boundaries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [GitHub OIDC subject claims](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect#understanding-the-oidc-token)
