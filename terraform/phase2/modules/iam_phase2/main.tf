data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# ── Lambda v2 Execution Role ──────────────────────────────────────────────────
resource "aws_iam_role" "lambda_v2_exec" {
  name        = "${var.project_name}-${var.environment}-phase2-lambda-exec"
  description = "Execution role for Lambda v2 - Phase 2 resources only"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_v2_exec" {
  name = "lambda-v2-exec-policy"
  role = aws_iam_role.lambda_v2_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-api-v2:*"
      },
      {
        Sid      = "DynamoDBV2"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:DeleteItem"]
        Resource = [var.dynamodb_v2_table_arn, "${var.dynamodb_v2_table_arn}/index/*"]
      },
      {
        Sid      = "SQSSend"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:GetQueueUrl"]
        Resource = var.sqs_queue_arn
      },
      {
        Sid      = "S3Reports"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${var.reports_bucket_arn}/*", "${var.sbom_bucket_arn}/*"]
      },
      # KMS statement removed 2026-07-16 -- Phase 2 CMK removed, resources now
      # use AWS-owned keys (no IAM grant needed for same-account principals).
      # See Phase3DeploymentPlanPoC.md item 9.
      {
        Sid      = "ECSRunTask"
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.project_name}-${var.environment}-scanner:*"
      },
      {
        Sid    = "IAMPassRoleToECS"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          aws_iam_role.fargate_task.arn,
          aws_iam_role.fargate_execution.arn,
        ]
      },
      {
        Sid      = "ECSCancelTask"
        Effect   = "Allow"
        Action   = ["ecs:ListTasks", "ecs:DescribeTasks", "ecs:StopTask"]
        Resource = "*"
      },
    ]
  })
}

# ── Fargate Task Role ─────────────────────────────────────────────────────────
resource "aws_iam_role" "fargate_task" {
  name        = "${var.project_name}-${var.environment}-phase2-fargate-task"
  description = "Task role for Fargate scanner - no access to Phase 1 resources"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "fargate_task" {
  name = "fargate-task-policy"
  role = aws_iam_role.fargate_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SQSConsume"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = var.sqs_queue_arn
      },
      {
        Sid      = "DynamoDBV2Write"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = var.dynamodb_v2_table_arn
      },
      {
        Sid      = "S3Write"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = ["${var.reports_bucket_arn}/*", "${var.sbom_bucket_arn}/*"]
      },
      # KMS statement removed 2026-07-16 -- see note above in lambda_v2_exec policy.
      {
        Sid    = "ECRScanAccess"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = "*"
      },
    ]
  })
}

# ── Fargate Task Execution Role ───────────────────────────────────────────────
resource "aws_iam_role" "fargate_execution" {
  name = "${var.project_name}-${var.environment}-phase2-fargate-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "fargate_execution_managed" {
  role       = aws_iam_role.fargate_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# fargate_execution_kms policy removed 2026-07-16 -- see KMS removal note above.

# ── GitHub Actions Role ───────────────────────────────────────────────────────
data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        # pull_request removed 2026-07-22 -- see threat model CRITICAL #1
        # (docs/SSAgent/DocImgAnalizer-AWSSecurityAgentThreatModelFindings-V1.md). This role has
        # broad write access (Terraform state, Lambda deploy, Cognito, API Gateway,
        # ECR push) and must only be assumable from merged/protected-branch context.
        # PR-time `terraform plan` now uses the separate, read-only
        # github_actions_plan role below instead.
        "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/phase2",
        "repo:${var.github_org}/${var.github_repo}:environment:phase2-development",
        "repo:${var.github_org}/${var.github_repo}:environment:phase2-production",
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-${var.environment}-phase2-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json
  description        = "Assumed by GitHub Actions via OIDC for Phase 2 CI/CD (deploy only, not PR plan)"
}

resource "aws_iam_role_policy" "github_actions" {
  name = "github-actions-phase2-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketVersioning"]
        Resource = [
          "arn:aws:s3:::${var.state_bucket}",
          "arn:aws:s3:::${var.state_bucket}/*",
        ]
      },
      {
        Sid    = "LambdaV2Deploy"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:PublishVersion",
          "lambda:UpdateAlias",
          "lambda:GetAlias",
        ]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-api-v2"
      },
      {
        Sid      = "ECSRegisterTask"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition", "ecs:UpdateService"]
        Resource = "*"
      },
      # ── Terraform management — Phase 2 resources ───────────────────────────
      # Terraform refresh/plan/apply needs read+write on every managed service.
      {
        Sid      = "TerraformManageCognito"
        Effect   = "Allow"
        Action   = ["cognito-idp:*"]
        Resource = "*"
      },
      {
        Sid      = "TerraformManageAPIGateway"
        Effect   = "Allow"
        Action   = ["apigateway:*"]
        Resource = "*"
      },
      {
        Sid      = "TerraformManageECR"
        Effect   = "Allow"
        Action   = ["ecr:DescribeRepositories", "ecr:CreateRepository", "ecr:DeleteRepository", "ecr:PutImageTagMutability", "ecr:PutLifecyclePolicy", "ecr:GetLifecyclePolicy", "ecr:DeleteLifecyclePolicy", "ecr:DescribeImages", "ecr:ListTagsForResource", "ecr:TagResource", "ecr:UntagResource"]
        Resource = "*"
      },
      {
        Sid      = "ECRAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project_name}-${var.environment}-scanner"
      },
      {
        Sid      = "TerraformManageECS"
        Effect   = "Allow"
        Action   = ["ecs:DescribeClusters", "ecs:CreateCluster", "ecs:DeleteCluster", "ecs:PutClusterCapacityProviders", "ecs:DescribeServices", "ecs:CreateService", "ecs:DeleteService", "ecs:DeregisterTaskDefinition", "ecs:ListTagsForResource", "ecs:TagResource"]
        Resource = "*"
      },
      {
        Sid      = "TerraformManageVPC"
        Effect   = "Allow"
        Action   = ["ec2:DescribeVpcs", "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute", "ec2:DescribeSubnets", "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:DescribeSecurityGroups", "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup", "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupEgress", "ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress", "ec2:DescribeInternetGateways", "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway", "ec2:DescribeRouteTables", "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:DeleteRoute", "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable", "ec2:DescribeVpcEndpoints", "ec2:CreateVpcEndpoint", "ec2:DeleteVpcEndpoints", "ec2:ModifyVpcEndpoint", "ec2:DescribeVpcEndpointServices", "ec2:DescribeSecurityGroupRules", "ec2:DescribeAvailabilityZones", "ec2:DescribeNetworkInterfaces", "ec2:DescribeNetworkAcls", "ec2:CreateTags", "ec2:DeleteTags", "ec2:DescribeTags", "ec2:DescribePrefixLists", "ec2:DescribeManagedPrefixLists", "ec2:GetManagedPrefixListEntries", "ec2:DescribeAddresses", "ec2:DescribeAddressesAttribute", "ec2:DescribeVpcAttribute", "ec2:AllocateAddress", "ec2:ReleaseAddress", "ec2:CreateNatGateway", "ec2:DeleteNatGateway", "ec2:DescribeNatGateways"]
        Resource = "*"
      },
      {
        Sid      = "TerraformManageSQS"
        Effect   = "Allow"
        Action   = ["sqs:CreateQueue", "sqs:DeleteQueue", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes", "sqs:GetQueueUrl", "sqs:ListQueueTags", "sqs:TagQueue", "sqs:UntagQueue"]
        Resource = "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.project_name}-${var.environment}-*"
      },
      # TerraformManageKMS removed 2026-07-16 -- Phase 2 no longer manages any
      # KMS resources (CMK removed, see Phase3DeploymentPlanPoC.md item 9).
      {
        Sid      = "TerraformManageIAM"
        Effect   = "Allow"
        Action   = ["iam:GetRole", "iam:CreateRole", "iam:DeleteRole", "iam:UpdateRole", "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies", "iam:TagRole", "iam:UntagRole", "iam:ListOpenIDConnectProviders", "iam:GetOpenIDConnectProvider", "iam:PassRole"]
        Resource = "*"
      },
      {
        Sid      = "TerraformManageLogs"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups", "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:ListTagsLogGroup", "logs:TagLogGroup", "logs:UntagLogGroup", "logs:ListTagsForResource", "logs:TagResource"]
        Resource = "*"
      },
      {
        Sid    = "TerraformManageS3Phase2"
        Effect = "Allow"
        # Explicit actions per IAM Access Analyzer + Terraform module audit (2026-07-16).
        # Covers all 6 aws_s3_bucket* resource types in modules/s3_phase2/main.tf.
        # ListBucket/OwnershipControls/PolicyStatus only fire on the create/replace
        # path (provider's HeadBucket-based create waiter + fresh-state Read), not
        # during steady-state refresh -- confirmed missing via simulate-principal-policy
        # after a live create-waiter failure, not visible in routine CloudTrail data.
        Action = [
          "s3:CreateBucket", "s3:DeleteBucket", "s3:GetBucketLocation",
          "s3:GetBucketTagging", "s3:PutBucketTagging", "s3:GetBucketAcl",
          "s3:GetBucketPolicy", "s3:GetBucketPolicyStatus", "s3:GetBucketRequestPayment", "s3:GetBucketLogging",
          "s3:GetBucketWebsite", "s3:GetReplicationConfiguration", "s3:GetBucketObjectLockConfiguration",
          "s3:GetAccelerateConfiguration", "s3:GetEncryptionConfiguration", "s3:PutEncryptionConfiguration",
          "s3:GetBucketVersioning", "s3:PutBucketVersioning", "s3:GetBucketCors",
          "s3:PutBucketCors", "s3:DeleteBucketCors", "s3:GetBucketPublicAccessBlock",
          "s3:PutBucketPublicAccessBlock", "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration",
          "s3:GetBucketOwnershipControls", "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-${var.environment}-cve-reports",
          "arn:aws:s3:::${var.project_name}-${var.environment}-sbom-reports",
          "arn:aws:s3:::${var.project_name}-${var.environment}-cve-reports/*",
          "arn:aws:s3:::${var.project_name}-${var.environment}-sbom-reports/*",
        ]
      },
      {
        Sid    = "TerraformManageFrontendS3"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.project_name}-${var.environment}-frontend",
          "arn:aws:s3:::${var.project_name}-${var.environment}-frontend/*",
        ]
      },
      {
        Sid      = "TerraformManageDynamoDB"
        Effect   = "Allow"
        Action   = ["dynamodb:DescribeTable", "dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:UpdateTable", "dynamodb:ListTagsOfResource", "dynamodb:TagResource", "dynamodb:UntagResource", "dynamodb:DescribeContinuousBackups", "dynamodb:UpdateContinuousBackups", "dynamodb:DescribeTimeToLive", "dynamodb:UpdateTimeToLive"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "TerraformManageLambda"
        Effect   = "Allow"
        Action   = ["lambda:*"]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "TerraformManagePipes"
        Effect   = "Allow"
        Action   = ["pipes:CreatePipe", "pipes:DeletePipe", "pipes:DescribePipe", "pipes:UpdatePipe", "pipes:ListTagsForResource", "pipes:TagResource", "pipes:UntagResource"]
        Resource = "arn:aws:pipes:${var.aws_region}:${data.aws_caller_identity.current.account_id}:pipe/${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "TerraformManageCloudWatch"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:DescribeAlarms", "cloudwatch:PutDashboard", "cloudwatch:DeleteDashboards", "cloudwatch:GetDashboard", "cloudwatch:ListTagsForResource", "cloudwatch:TagResource"]
        Resource = "*"
      },
      {
        Sid      = "TerraformManageSNS"
        Effect   = "Allow"
        Action   = ["sns:GetTopicAttributes", "sns:CreateTopic", "sns:DeleteTopic", "sns:SetTopicAttributes", "sns:TagResource", "sns:UntagResource", "sns:ListTagsForResource", "sns:Subscribe", "sns:Unsubscribe", "sns:GetSubscriptionAttributes"]
        Resource = "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "CloudFrontInvalidation"
        Effect   = "Allow"
        Action   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
        Resource = "*"
      },
    ]
  })
}

# ── PR-time read-only role (Step 1 of threat model CRITICAL #1 fix) ──────────
# Separate role, trusted only for `pull_request`, so an external/forked PR can
# never obtain write credentials -- only enough read access for `terraform
# plan`. Hand-mirrored from every statement in the github_actions write policy
# above: same resource ARN scoping, actions swapped for their Describe/Get/List
# equivalents. Built by inference, not from an observed CloudTrail window (Step
# 9's Access Analyzer approach doesn't apply here -- this role doesn't exist
# yet, so there's no usage history to generate from). If a future PR-time plan
# hits AccessDenied on a read action missed here, add that one specific
# permission -- same iterative least-privilege pattern as Step 9.
data "aws_iam_policy_document" "github_actions_plan_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:pull_request"]
    }
  }
}

resource "aws_iam_role" "github_actions_plan" {
  name               = "${var.project_name}-${var.environment}-phase2-github-actions-plan"
  assume_role_policy = data.aws_iam_policy_document.github_actions_plan_assume.json
  description        = "Assumed by GitHub Actions via OIDC for Phase 2 PR-time terraform plan only -- read-only, no deploy credentials"
}

resource "aws_iam_role_policy" "github_actions_plan" {
  name = "github-actions-phase2-plan-policy"
  role = aws_iam_role.github_actions_plan.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "TerraformStateRead"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket", "s3:GetBucketVersioning"]
        Resource = ["arn:aws:s3:::${var.state_bucket}", "arn:aws:s3:::${var.state_bucket}/*"]
      },
      {
        Sid      = "LambdaV2Read"
        Effect   = "Allow"
        Action   = ["lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:GetAlias"]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-api-v2"
      },
      {
        Sid      = "ECSRead"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTaskDefinition", "ecs:DescribeClusters", "ecs:DescribeServices", "ecs:ListTagsForResource"]
        Resource = "*"
      },
      {
        Sid      = "CognitoRead"
        Effect   = "Allow"
        Action   = ["cognito-idp:Describe*", "cognito-idp:Get*", "cognito-idp:List*"]
        Resource = "*"
      },
      {
        Sid      = "APIGatewayRead"
        Effect   = "Allow"
        Action   = ["apigateway:GET"]
        Resource = "*"
      },
      {
        Sid      = "ECRRead"
        Effect   = "Allow"
        Action   = ["ecr:DescribeRepositories", "ecr:DescribeImages", "ecr:ListTagsForResource", "ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
        Resource = "*"
      },
      {
        Sid      = "VPCRead"
        Effect   = "Allow"
        Action   = ["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeSecurityGroupRules", "ec2:DescribeInternetGateways", "ec2:DescribeRouteTables", "ec2:DescribeVpcEndpoints", "ec2:DescribeVpcEndpointServices", "ec2:DescribeAvailabilityZones", "ec2:DescribeNetworkInterfaces", "ec2:DescribeNetworkAcls", "ec2:DescribeTags", "ec2:DescribePrefixLists", "ec2:DescribeManagedPrefixLists", "ec2:GetManagedPrefixListEntries", "ec2:DescribeAddresses", "ec2:DescribeAddressesAttribute", "ec2:DescribeVpcAttribute", "ec2:DescribeNatGateways"]
        Resource = "*"
      },
      {
        Sid      = "SQSRead"
        Effect   = "Allow"
        Action   = ["sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ListQueueTags"]
        Resource = "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "IAMRead"
        Effect   = "Allow"
        Action   = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies", "iam:ListOpenIDConnectProviders", "iam:GetOpenIDConnectProvider"]
        Resource = "*"
      },
      {
        Sid      = "LogsRead"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups", "logs:ListTagsLogGroup", "logs:ListTagsForResource"]
        Resource = "*"
      },
      {
        Sid    = "S3Phase2Read"
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation", "s3:GetBucketTagging", "s3:GetBucketAcl", "s3:GetBucketPolicy",
          "s3:GetBucketPolicyStatus", "s3:GetBucketRequestPayment", "s3:GetBucketLogging",
          "s3:GetBucketWebsite", "s3:GetReplicationConfiguration", "s3:GetBucketObjectLockConfiguration",
          "s3:GetAccelerateConfiguration", "s3:GetEncryptionConfiguration", "s3:GetBucketVersioning",
          "s3:GetBucketCors", "s3:GetBucketPublicAccessBlock", "s3:GetLifecycleConfiguration",
          "s3:GetBucketOwnershipControls", "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-${var.environment}-cve-reports",
          "arn:aws:s3:::${var.project_name}-${var.environment}-sbom-reports",
          "arn:aws:s3:::${var.project_name}-${var.environment}-cve-reports/*",
          "arn:aws:s3:::${var.project_name}-${var.environment}-sbom-reports/*",
        ]
      },
      {
        Sid      = "FrontendS3Read"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = ["arn:aws:s3:::${var.project_name}-${var.environment}-frontend", "arn:aws:s3:::${var.project_name}-${var.environment}-frontend/*"]
      },
      {
        Sid      = "DynamoDBRead"
        Effect   = "Allow"
        Action   = ["dynamodb:DescribeTable", "dynamodb:ListTagsOfResource", "dynamodb:DescribeContinuousBackups", "dynamodb:DescribeTimeToLive"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "LambdaRead"
        Effect   = "Allow"
        Action   = ["lambda:Get*", "lambda:List*"]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "PipesRead"
        Effect   = "Allow"
        Action   = ["pipes:DescribePipe", "pipes:ListTagsForResource"]
        Resource = "arn:aws:pipes:${var.aws_region}:${data.aws_caller_identity.current.account_id}:pipe/${var.project_name}-${var.environment}-*"
      },
      {
        Sid      = "CloudWatchRead"
        Effect   = "Allow"
        Action   = ["cloudwatch:DescribeAlarms", "cloudwatch:GetDashboard", "cloudwatch:ListTagsForResource"]
        Resource = "*"
      },
      {
        Sid      = "SNSRead"
        Effect   = "Allow"
        Action   = ["sns:GetTopicAttributes", "sns:ListTagsForResource", "sns:GetSubscriptionAttributes"]
        Resource = "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.project_name}-${var.environment}-*"
      },
    ]
  })
}
