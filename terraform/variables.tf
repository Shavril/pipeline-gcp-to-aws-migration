variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used as a prefix for AWS resource names."
  type        = string
  default     = "pipeline-gcp-to-aws"
}
