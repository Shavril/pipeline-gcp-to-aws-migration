# Object storage for the local pipeline's Parquet output.
# Bucket name is suffixed with the account ID since S3 bucket
# names are globally unique.

resource "aws_s3_bucket" "pipeline" {
  bucket = "${var.project_name}-migration-${data.aws_caller_identity.current.account_id}"

  # Lets `terraform destroy` empty the bucket first instead of refusing to
  # delete a non-empty bucket - needed since the pipeline's Parquet output
  # lands here and this bucket is meant to be disposable: the real source
  # of truth is the local Parquet files and Redshift, not this bucket.
  force_destroy = true
}

# Both settings below are AWS's own defaults for a new bucket - declared
# explicitly anyway so the intended security posture is documented in code.

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
