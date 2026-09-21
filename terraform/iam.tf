# Role Redshift Serverless assumes to read the pipeline's S3 bucket during
# COPY. Scoped to just this bucket, not account-wide S3 read access.

data "aws_iam_policy_document" "redshift_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "redshift_s3_read" {
  name               = "${var.project_name}-redshift-s3-read"
  description        = "Redshift Serverless namespace role: read-only access to the pipeline S3 bucket for COPY"
  assume_role_policy = data.aws_iam_policy_document.redshift_trust.json
}

data "aws_iam_policy_document" "redshift_s3_read" {
  statement {
    sid    = "ReadPipelineBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.pipeline.arn,
      "${aws_s3_bucket.pipeline.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "redshift_s3_read" {
  name   = "read-pipeline-bucket"
  role   = aws_iam_role.redshift_s3_read.id
  policy = data.aws_iam_policy_document.redshift_s3_read.json
}
