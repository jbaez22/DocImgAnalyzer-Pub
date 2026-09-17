locals {
  reports_bucket = "${var.project_name}-${var.environment}-cve-reports"
  sbom_bucket    = "${var.project_name}-${var.environment}-sbom-reports"
}

# ── CVE Reports Bucket ────────────────────────────────────────────────────────
resource "aws_s3_bucket" "reports" {
  bucket = local.reports_bucket
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3 (AES256, AWS-owned key, free) -- CMK removed 2026-07-16
      # per Phase3DeploymentPlanPoC.md item 9
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    id     = "expire-old-reports"
    status = "Enabled"
    filter {}
    expiration { days = 365 }
  }
}

resource "aws_s3_bucket_cors_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  cors_rule {
    allowed_origins = [var.frontend_origin]
    allowed_methods = ["GET"]
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}

# ── SBOM Bucket ───────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "sbom" {
  bucket = local.sbom_bucket
}

resource "aws_s3_bucket_versioning" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3 (AES256, AWS-owned key, free) -- CMK removed 2026-07-16
      # per Phase3DeploymentPlanPoC.md item 9
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "sbom" {
  bucket                  = aws_s3_bucket.sbom.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  rule {
    id     = "expire-old-sboms"
    status = "Enabled"
    filter {}
    expiration { days = 365 }
  }
}

resource "aws_s3_bucket_cors_configuration" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  cors_rule {
    allowed_origins = [var.frontend_origin]
    allowed_methods = ["GET"]
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}
