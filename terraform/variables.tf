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
