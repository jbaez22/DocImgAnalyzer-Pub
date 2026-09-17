resource "aws_dynamodb_table" "scans" {
  name         = "${var.project_name}-${var.environment}-scans"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "scan_id"
  range_key    = "created_at"

  attribute {
    name = "scan_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}
