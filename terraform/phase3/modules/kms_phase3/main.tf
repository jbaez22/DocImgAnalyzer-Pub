data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_kms_key" "phase3" {
  description             = "${var.project_name}-${var.environment}-phase3 - Phase 3 CMK for DynamoDB v3 and Secrets Manager"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  lifecycle {
    ignore_changes = [description]
  }

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RootAccountFullAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowSecretsManagerService"
        Effect = "Allow"
        Principal = {
          Service = "secretsmanager.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:CallerAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
    ]
  })
}

resource "aws_kms_alias" "phase3" {
  name          = "alias/${var.project_name}-${var.environment}-phase3"
  target_key_id = aws_kms_key.phase3.key_id
}
