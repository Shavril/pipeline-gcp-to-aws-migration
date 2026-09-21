# Dedicated security group for Looker Studio's native Redshift connector,
# kept separate from the default VPC security group so this one narrow
# opening is easy to find, audit, and remove independently.
#
# Why this exists: Looker Studio's connector needs a direct network
# connection (it doesn't support the Redshift Data API/IAM auth used
# everywhere else in this project, which required making the workgroup publicly
# accessible (see redshift.tf). This security group is what keeps that
# opening narrow: only Looker Studio's own published IP range, only the
# Redshift port.
resource "aws_security_group" "looker_studio" {
  name        = "${var.project_name}-looker-studio"
  description = "Allow Looker Studio published IP range to reach Redshift Serverless on 5439"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "${var.project_name}-looker-studio"
  }
}

# Looker Studio's published IP range for its Amazon Redshift connector
# (global infrastructure). Source:
# https://docs.cloud.google.com/looker/docs/studio/connect-to-amazon-redshift
resource "aws_vpc_security_group_ingress_rule" "looker_studio_redshift" {
  security_group_id = aws_security_group.looker_studio.id
  cidr_ipv4         = "142.251.74.0/23"
  from_port         = 5439
  to_port           = 5439
  ip_protocol       = "tcp"
}

# Default allow-all egress, auto-created by AWS when the security group was made.
resource "aws_vpc_security_group_egress_rule" "looker_studio_all" {
  security_group_id = aws_security_group.looker_studio.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
