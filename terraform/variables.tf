variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Portfolio project showing migration of a pipeline from GCP to AWS."
  type        = string
  default     = "pipeline-gcp-to-aws"
}

variable "github_org" {
  description = "GitHub org/user that owns the repo allowed to assume the deploy role via OIDC."
  type        = string
  default     = "Shavril"
}

variable "github_repo" {
  description = "GitHub repo name allowed to assume the deploy role via OIDC."
  type        = string
  default     = "pipeline-gcp-to-aws-migration"
}
