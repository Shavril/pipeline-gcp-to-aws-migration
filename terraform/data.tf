# Referenced, not managed: this project deliberately uses the account's
# existing default VPC/subnets rather than creating dedicated networking.
# Terraform reads them as data sources so it never tries to create or destroy them.

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_security_group" "default" {
  vpc_id = data.aws_vpc.default.id
  name   = "default"
}

# Redshift Serverless requires subnets in at least 3 distinct AZs. Pinned to
# the 3 specific AZs already in use by the live workgroup (one default-VPC
# subnet each) rather than picking arbitrarily, so this matches the real
# resource exactly instead of just satisfying the "3 AZs" minimum some other way.
data "aws_subnets" "redshift" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "availability-zone"
    values = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  }
}
