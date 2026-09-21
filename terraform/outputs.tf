output "s3_bucket_name" {
  description = "Set as OIL_PIPELINE_S3_BUCKET_NAME in .env."
  value       = aws_s3_bucket.pipeline.id
}

output "redshift_workgroup_name" {
  description = "Set as OIL_PIPELINE_REDSHIFT_WORKGROUP_NAME in .env."
  value       = aws_redshiftserverless_workgroup.pipeline.workgroup_name
}

output "redshift_database_name" {
  description = "Set as OIL_PIPELINE_REDSHIFT_DATABASE_NAME in .env."
  value       = aws_redshiftserverless_namespace.pipeline.db_name
}

output "redshift_s3_role_arn" {
  description = "Set as OIL_PIPELINE_REDSHIFT_S3_ROLE_ARN in .env."
  value       = aws_iam_role.redshift_s3_read.arn
}

output "redshift_endpoint" {
  description = "Host:port for Looker Studio's Basic connection."
  value       = "${aws_redshiftserverless_workgroup.pipeline.endpoint[0].address}:${aws_redshiftserverless_workgroup.pipeline.endpoint[0].port}"
}
