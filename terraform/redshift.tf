# Redshift Serverless replaces BigQuery, because it has free connector to
# existing Data Studio dashboard.
#
# No admin username/password is set (no manage_admin_password either) -
# deliberately, so the only way in is the standard AWS credential chain via
# the Redshift Data API (IAM auth). The schema/tables/views/grants and
# the looker_reader database user created for Data Studio's connector
# are in-database SQL objects, not AWS resources - they're managed by
# the pipeline code (oil_pipeline.load.redshift) and one-time setup SQL.
resource "aws_redshiftserverless_namespace" "pipeline" {
  namespace_name       = var.project_name
  db_name              = "dev"
  iam_roles            = [aws_iam_role.redshift_s3_read.arn]
  default_iam_role_arn = aws_iam_role.redshift_s3_read.arn
}

# Base capacity is the current AWS minimum (4 RPU, ~$0.375/RPU-hour in
# us-east-1). Billed per-second while actively processing queries only.
#
# publicly_accessible = true and the dedicated Data Studio security group
# (see security_groups.tf) exist only because Data Studio's native
# connector needs direct network access - everything else in this project
# (the pipeline's own S3->Redshift load) uses the Data API and never
# touches the network path this opens.
resource "aws_redshiftserverless_workgroup" "pipeline" {
  namespace_name      = aws_redshiftserverless_namespace.pipeline.namespace_name
  workgroup_name      = var.project_name
  base_capacity       = 4
  publicly_accessible = true
  subnet_ids          = data.aws_subnets.redshift.ids
  security_group_ids = [
    data.aws_security_group.default.id,
    aws_security_group.looker_studio.id,
  ]
}
