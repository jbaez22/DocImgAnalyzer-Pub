data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_kms_key" "main" {
  description             = "CMK for ${var.project_name}-${var.environment} -- DynamoDB, S3 reports, Lambda env vars, SNS alerts"
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = true

  # Ignore description changes — cosmetic updates trigger kms:UpdateKeyDescription
  # which requires a separate IAM propagation cycle and causes intermittent deploy failures.
  lifecycle {
    ignore_changes = [description]
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowLambdaService"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchService"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.project_name}-${var.environment}"
  target_key_id = aws_kms_key.main.key_id
}
