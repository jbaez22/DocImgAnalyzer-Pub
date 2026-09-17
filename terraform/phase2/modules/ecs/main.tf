data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_log_group" "scanner" {
  name              = "/ecs/${var.project_name}-${var.environment}-scanner"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}-phase2"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "scanner" {
  family                   = "${var.project_name}-${var.environment}-scanner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.fargate_cpu
  memory                   = var.fargate_memory
  task_role_arn            = var.task_role_arn
  execution_role_arn       = var.execution_role_arn

  container_definitions = jsonencode([{
    name      = "scanner"
    image     = var.scanner_image
    essential = true

    environment = [
      { name = "DYNAMODB_TABLE", value = var.dynamodb_v2_table_name },
      { name = "REPORTS_BUCKET", value = var.reports_bucket_id },
      { name = "SBOM_BUCKET", value = var.sbom_bucket_id },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.scanner.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "scanner"
      }
    }
  }])

  lifecycle {
    ignore_changes = [container_definitions]
  }
}

# ── EventBridge Pipe: SQS → ECS Fargate ──────────────────────────────────────
# Polls SQS and launches one Fargate task per message batch.
resource "aws_pipes_pipe" "sqs_to_fargate" {
  name     = "${var.project_name}-${var.environment}-scan-trigger"
  role_arn = aws_iam_role.pipe.arn
  source   = var.sqs_queue_arn

  # task_definition_arn and network_configuration are updated by the pipeline
  # after each scanner image push — ignore_changes prevents Terraform from
  # reverting to the initial revision on subsequent applies.
  lifecycle {
    ignore_changes = [target_parameters]
  }

  source_parameters {
    sqs_queue_parameters {
      batch_size = 1
    }
  }

  target = aws_ecs_cluster.main.arn

  target_parameters {
    ecs_task_parameters {
      task_definition_arn = aws_ecs_task_definition.scanner.arn
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        aws_vpc_configuration {
          subnets          = var.private_subnet_ids
          security_groups  = [var.fargate_task_sg_id]
          assign_public_ip = var.assign_public_ip
        }
      }

      overrides {
        container_override {
          name = "scanner"
          environment {
            name  = "SQS_MESSAGE"
            value = "<$.body>"
          }
        }
      }
    }
  }
}

resource "aws_iam_role" "pipe" {
  name = "${var.project_name}-${var.environment}-phase2-pipe"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pipes.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "pipe" {
  name = "pipe-policy"
  role = aws_iam_role.pipe.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SQSRead"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = var.sqs_queue_arn
      },
      {
        Sid      = "ECSRun"
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = "arn:aws:ecs:${var.aws_region}:*:task-definition/${var.project_name}-${var.environment}-scanner:*"
      },
      {
        Sid      = "IAMPassRole"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [var.task_role_arn, var.execution_role_arn]
      },
      # KMSDecrypt statement removed 2026-07-16 -- SQS now uses the AWS-owned
      # key (free), which needs no explicit IAM grant for same-account
      # principals. See Phase3DeploymentPlanPoC.md item 9.
    ]
  })
}
