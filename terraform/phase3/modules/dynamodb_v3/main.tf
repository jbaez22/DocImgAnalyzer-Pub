resource "aws_dynamodb_table" "subscriptions" {
  name         = "${var.project_name}-${var.environment}-subscriptions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "stripe_customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "stripe-customer-index"
    hash_key        = "stripe_customer_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}

resource "aws_dynamodb_table" "api_keys" {
  name         = "${var.project_name}-${var.environment}-api-keys"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "key_id"

  attribute {
    name = "key_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "key_hash"
    type = "S"
  }

  global_secondary_index {
    name            = "user-keys-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "key-hash-index"
    hash_key        = "key_hash"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}

resource "aws_dynamodb_table" "orgs" {
  name         = "${var.project_name}-${var.environment}-orgs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "org_id"

  attribute {
    name = "org_id"
    type = "S"
  }

  attribute {
    name = "admin_user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "admin-org-index"
    hash_key        = "admin_user_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}
