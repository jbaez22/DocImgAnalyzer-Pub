data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# ── Lambda v3 Execution Role ──────────────────────────────────────────────────
resource "aws_iam_role" "lambda_v3_exec" {
  name        = "${var.project_name}-${var.environment}-phase3-lambda-exec"
  description = "Execution role for Lambda v3 - Phase 3 resources only"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_v3_exec" {
  name = "lambda-v3-exec-policy"
  role = aws_iam_role.lambda_v3_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-api-v3:*"
      },
      {
        Sid    = "DynamoDBV3"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:DeleteItem"]
        Resource = [
          var.subscriptions_table_arn, "${var.subscriptions_table_arn}/index/*",
          var.api_keys_table_arn, "${var.api_keys_table_arn}/index/*",
          var.orgs_table_arn, "${var.orgs_table_arn}/index/*",
        ]
      },
      {
        Sid      = "DynamoDBV2"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [var.phase2_dynamodb_v2_table_arn, "${var.phase2_dynamodb_v2_table_arn}/index/*"]
      },
      {
        Sid      = "SQSSend"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:GetQueueUrl"]
        Resource = var.phase2_sqs_queue_arn
      },
      {
        Sid      = "SecretsManagerStripe"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.stripe_secret_key_arn
      },
      {
        Sid      = "CognitoUpdateUser"
        Effect   = "Allow"
        Action   = ["cognito-idp:AdminUpdateUserAttributes", "cognito-idp:AdminGetUser"]
        Resource = var.cognito_user_pool_arn
      },
      {
        Sid      = "KMSPhase3"
        Effect   = "Allow"
        Action   = ["kms:GenerateDataKey", "kms:Decrypt"]
        Resource = var.kms_key_arn
      },
      # KMSPhase2SQS removed 2026-07-16 -- Phase 2's SQS queue now uses the
      # AWS-owned key (CMK removed, Phase3DeploymentPlanPoC.md item 9), which
      # needs no explicit IAM grant for same-account principals.
    ]
  })
}

# ── Stripe Webhook Lambda Execution Role ──────────────────────────────────────
resource "aws_iam_role" "stripe_webhook_exec" {
  name        = "${var.project_name}-${var.environment}-stripe-webhook-exec"
  description = "Execution role for Stripe webhook Lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "stripe_webhook_exec" {
  name = "stripe-webhook-exec-policy"
  role = aws_iam_role.stripe_webhook_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-stripe-webhook:*"
      },
      {
        Sid      = "DynamoDBSubscriptions"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [var.subscriptions_table_arn, "${var.subscriptions_table_arn}/index/*"]
      },
      {
        Sid      = "SecretsManagerStripe"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.stripe_secret_key_arn, var.stripe_webhook_secret_arn]
      },
      {
        Sid      = "CognitoUpdateUser"
        Effect   = "Allow"
        Action   = ["cognito-idp:AdminUpdateUserAttributes"]
        Resource = var.cognito_user_pool_arn
      },
      {
        Sid      = "KMSPhase3"
        Effect   = "Allow"
        Action   = ["kms:GenerateDataKey", "kms:Decrypt"]
        Resource = var.kms_key_arn
      },
    ]
  })
}

# ── EventBridge Scheduler Role ────────────────────────────────────────────────
resource "aws_iam_role" "eventbridge_scheduler" {
  name        = "${var.project_name}-${var.environment}-phase3-scheduler"
  description = "EventBridge Scheduler role for nightly re-scan trigger"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_scheduler" {
  name = "scheduler-policy"
  role = aws_iam_role.eventbridge_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "LambdaInvoke"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-rescan-trigger*"
      },
    ]
  })
}

# ── Re-scan Trigger Lambda Execution Role ─────────────────────────────────────
resource "aws_iam_role" "rescan_trigger_exec" {
  name        = "${var.project_name}-${var.environment}-rescan-trigger-exec"
  description = "Execution role for nightly re-scan trigger Lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "rescan_trigger_exec" {
  name = "rescan-trigger-policy"
  role = aws_iam_role.rescan_trigger_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-rescan-trigger:*"
      },
      {
        Sid      = "DynamoDBSubscriptionsRead"
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:Scan"]
        Resource = [var.subscriptions_table_arn, "${var.subscriptions_table_arn}/index/*"]
      },
      {
        Sid    = "DynamoDBScansV2"
        Effect = "Allow"
        Action = ["dynamodb:Query", "dynamodb:PutItem"]
        Resource = [
          var.phase2_dynamodb_v2_table_arn,
          "${var.phase2_dynamodb_v2_table_arn}/index/*",
        ]
      },
      {
        Sid    = "ECSRunTask"
        Effect = "Allow"
        Action = ["ecs:RunTask"]
        Resource = [
          "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.project_name}-${var.environment}-scanner:*",
        ]
      },
      {
        Sid    = "IAMPassFargate"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-${var.environment}-phase2-fargate-*",
        ]
      },
      {
        Sid      = "KMSPhase3"
        Effect   = "Allow"
        Action   = ["kms:GenerateDataKey", "kms:Decrypt"]
        Resource = var.kms_key_arn
      },
      # KMSPhase2DB removed 2026-07-16 -- Phase 2's scans-v2 table now uses
      # the AWS-owned key (CMK removed, Phase3DeploymentPlanPoC.md item 9),
      # which needs no explicit IAM grant for same-account principals.
    ]
  })
}

# ── GitHub Actions Role ───────────────────────────────────────────────────────
resource "aws_iam_role" "github_actions" {
  name        = "${var.project_name}-${var.environment}-phase3-github-actions"
  description = "GitHub Actions OIDC role for Phase 3 CI/CD - Phase 3 resources only"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = data.aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main",
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/develop",
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/phase3",
            "repo:${var.github_org}/${var.github_repo}:pull_request",
            # Environment-scoped sub claims (GitHub uses full name, not tfvar shorthand)
            "repo:${var.github_org}/${var.github_repo}:environment:phase3-development",
            "repo:${var.github_org}/${var.github_repo}:environment:phase3-production",
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_actions" {
  name = "phase3-github-actions-policy"
  role = aws_iam_role.github_actions.id

  # Full actions on phase3 resources only — harden with IAM Access Analyzer post-MVP.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # No phase's IAM role creates the state bucket itself (bootstrap resource) —
        # object CRUD + versioning read only, matches phase2's TerraformState statement.
        Sid    = "S3TerraformStateAllPhases"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketVersioning"]
        Resource = [
          "arn:aws:s3:::${var.state_bucket}",
          "arn:aws:s3:::${var.state_bucket}/*",
        ]
      },
      {
        # Phase 1 owns/creates the frontend and reports buckets — phase3 only needs
        # object CRUD, matches phase2's TerraformManageFrontendS3 statement.
        Sid    = "S3FrontendReports"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.project_name}-${var.environment}-frontend",
          "arn:aws:s3:::${var.project_name}-${var.environment}-frontend/*",
          "arn:aws:s3:::${var.project_name}-${var.environment}-reports",
          "arn:aws:s3:::${var.project_name}-${var.environment}-reports/*",
        ]
      },
      {
        # iam:List* on OIDC provider requires Resource: * (AWS-enforced)
        Sid      = "IAMOIDCRead"
        Effect   = "Allow"
        Action   = ["iam:ListOpenIDConnectProviders", "iam:GetOpenIDConnectProvider"]
        Resource = ["*"]
      },
      {
        Sid    = "IAMPhase3Roles"
        Effect = "Allow"
        Action = ["iam:*"]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-${var.environment}-phase3-*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-${var.environment}-stripe-webhook-*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-${var.environment}-rescan-trigger-*",
        ]
      },
      {
        # ListAliases / ListKeys are list ops — AWS enforces Resource: * for them
        Sid      = "KMSListGlobal"
        Effect   = "Allow"
        Action   = ["kms:ListAliases", "kms:ListKeys", "kms:ListResourceTags"]
        Resource = ["*"]
      },
      {
        Sid    = "KMSPhase3"
        Effect = "Allow"
        Action = ["kms:*"]
        Resource = [
          "arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:key/*",
          "arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alias/${var.project_name}-${var.environment}-*",
        ]
      },
      {
        # DescribeLogGroups is a list op — AWS enforces Resource: * for it
        Sid      = "LogsDescribeGlobal"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups", "logs:DescribeLogStreams"]
        Resource = ["*"]
      },
      {
        Sid    = "LogsPhase3"
        Effect = "Allow"
        Action = ["logs:*"]
        Resource = [
          "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-*",
          "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-*:*",
        ]
      },
      {
        Sid    = "LambdaPhase3"
        Effect = "Allow"
        Action = ["lambda:*"]
        Resource = [
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-api-v3*",
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-stripe-webhook*",
          "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.environment}-rescan-trigger*",
        ]
      },
      {
        Sid    = "APIGatewayPhase3"
        Effect = "Allow"
        Action = ["apigateway:*"]
        Resource = [
          "arn:aws:apigateway:${var.aws_region}::/apis/*",
          "arn:aws:apigateway:${var.aws_region}::/apis",
        ]
      },
      {
        Sid    = "DynamoDBPhase3"
        Effect = "Allow"
        Action = ["dynamodb:*"]
        Resource = [
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-subscriptions",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-subscriptions/*",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-api-keys",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-api-keys/*",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-orgs",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-orgs/*",
        ]
      },
      {
        Sid    = "SecretsManagerStripe"
        Effect = "Allow"
        Action = ["secretsmanager:*"]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:img-analyzer/${var.environment}/stripe/*",
        ]
      },
      {
        # ListSchedules is a list op — AWS enforces Resource: * for it
        Sid      = "SchedulerListGlobal"
        Effect   = "Allow"
        Action   = ["scheduler:ListSchedules", "scheduler:ListScheduleGroups"]
        Resource = ["*"]
      },
      {
        Sid    = "SchedulerPhase3"
        Effect = "Allow"
        Action = ["scheduler:*"]
        Resource = [
          # Named schedule groups
          "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule-group/${var.project_name}-${var.environment}-*",
          "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule-group/default",
          # Schedules in named groups and in the default group
          "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/${var.project_name}-${var.environment}-*/*",
          "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/default/${var.project_name}-${var.environment}-*",
        ]
      },
      {
        Sid    = "CloudWatchDashboard"
        Effect = "Allow"
        Action = ["cloudwatch:*"]
        Resource = [
          "arn:aws:cloudwatch::${data.aws_caller_identity.current.account_id}:dashboard/${var.project_name}-${var.environment}-*",
        ]
      },
      {
        # DescribeAlarms also works as a list op and may need * — include both scoped and *
        Sid      = "CloudWatchAlarmsDescribeGlobal"
        Effect   = "Allow"
        Action   = ["cloudwatch:DescribeAlarms", "cloudwatch:DescribeAlarmsForMetric"]
        Resource = ["*"]
      },
      {
        Sid    = "CloudWatchAlarms"
        Effect = "Allow"
        Action = ["cloudwatch:*"]
        Resource = [
          "arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alarm:${var.project_name}-${var.environment}-phase3-*",
        ]
      },
      {
        Sid    = "CloudFrontInvalidation"
        Effect = "Allow"
        Action = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation",
          "cloudfront:GetDistribution", "cloudfront:GetDistributionConfig",
        "cloudfront:ListInvalidations"]
        Resource = [
          "arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/*",
        ]
      },
      {
        Sid      = "TerraformStateLock"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:DescribeTable"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.state_lock_table}"
      },
    ]
  })
}
