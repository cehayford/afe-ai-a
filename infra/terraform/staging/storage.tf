# Buckets split by sensitivity (Statement §8.6). The backups bucket lives in a separate
# AWS account and is not managed from this stack.

resource "aws_kms_key" "kyc" {
  description             = "${local.name}: Ghana Card and ownership documents"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "kyc" {
  name          = "alias/${local.name}-kyc"
  target_key_id = aws_kms_key.kyc.key_id
}

locals {
  buckets = {
    media_public    = "${local.name}-media-public"    # processed listing photos, via CloudFront only
    media_originals = "${local.name}-media-originals" # raw uploads, kept as fraud evidence
    kyc_private     = "${local.name}-kyc-private"     # identity and ownership documents
    documents       = "${local.name}-documents"       # tenancy agreements, receipts (Phase 2)
  }
}

resource "aws_s3_bucket" "this" {
  for_each      = local.buckets
  bucket        = each.value
  force_destroy = false
  # Object Lock can only be switched on at creation.
  object_lock_enabled = each.key == "documents"
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = aws_s3_bucket.this
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = { for k, v in aws_s3_bucket.this : k => v if k != "media_public" } # public copies can be rebuilt
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = each.key == "kyc_private" ? "aws:kms" : "AES256"
      kms_master_key_id = each.key == "kyc_private" ? aws_kms_key.kyc.arn : null
    }
    bucket_key_enabled = each.key == "kyc_private"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "originals" {
  bucket = aws_s3_bucket.this["media_originals"].id
  rule {
    id     = "cheaper-storage-after-90-days"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "documents" {
  bucket = aws_s3_bucket.this["documents"].id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 365 # set with counsel under Act 843 (decision D18)
    }
  }
  depends_on = [aws_s3_bucket_versioning.this]
}

# --- Public photos through CloudFront (Origin Access Control; the bucket stays private) ---

resource "aws_cloudfront_origin_access_control" "media" {
  name                              = "${local.name}-media"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "media" {
  enabled         = true
  comment         = "${local.name} listing photos"
  is_ipv6_enabled = true
  price_class     = "PriceClass_All" # includes edge locations nearest Accra

  origin {
    domain_name              = aws_s3_bucket.this["media_public"].bucket_regional_domain_name
    origin_id                = "media"
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  default_cache_behavior {
    target_origin_id       = "media"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6" # AWS managed CachingOptimized
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "media_public" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this["media_public"].arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.media.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "media_public" {
  bucket = aws_s3_bucket.this["media_public"].id
  policy = data.aws_iam_policy_document.media_public.json
}
