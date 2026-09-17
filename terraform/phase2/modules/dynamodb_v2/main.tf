resource "aws_dynamodb_table" "scans_v2" {
  name         = "${var.project_name}-${var.environment}-scans-v2"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "scan_id"

  attribute {
    name = "scan_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "user-scans-index"
    hash_key        = "user_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  # AWS-owned key (free) -- CMK removed 2026-07-16 per Phase3DeploymentPlanPoC.md item 9
  server_side_encryption {
    enabled = true
  }
}
