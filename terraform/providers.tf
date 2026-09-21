terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Remote state so the local dev machine and GitHub Actions share the same
  # source of truth - a fresh CI checkout has no local state file, so
  # without this every deploy-terraform run would think nothing exists yet
  # and try to recreate everything, colliding with the real resources.
  #
  # Backend blocks can't reference variables, so the bucket name/region are
  # literal here rather than var.project_name/var.aws_region. This bucket
  # is a separate, manually-created bootstrap resource, deliberately not
  # managed by this Terraform config - state must not live inside anything
  # Terraform itself could destroy (see terraform/README.md).
  #
  # use_lockfile uses S3's own conditional writes for locking (Terraform
  # 1.10+) - no DynamoDB table needed.
  backend "s3" {
    bucket       = "pipeline-gcp-to-aws-migration-tfstate-740948698458"
    key          = "terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}
