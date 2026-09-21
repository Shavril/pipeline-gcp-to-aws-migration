# Terraform: AWS infrastructure

Codifies the AWS resources this project's local pipeline depends on: S3 bucket, Redshift
Serverless namespace/workgroup, the IAM role Redshift uses to read S3, and the security
group that lets Looker Studio's native connector reach Redshift.

Every resource here was built and verified manually first, then imported
into Terraform state rather than recreated - `terraform plan` shows zero diff against
the live resources.

## Prerequisites: IAM permissions for whoever runs Terraform

The local dev IAM user that runs `terraform` here needs this permission set. It was
discovered during a `destroy`/`apply` test.

**AWS managed policies, attached directly:**
- `AmazonS3FullAccess`
- `AmazonRedshiftFullAccess`
- `AmazonRedshiftDataFullAccess`
- `IAMFullAccess`

**One inline policy** (name doesn't matter, e.g. `ec2-security-group-management`) -
none of the managed policies above cover EC2/VPC actions, which Terraform needs for the
security group and for its `aws_vpc`/`aws_subnets` data sources:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecurityGroupManagementUsEast1",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSecurityGroupRules",
        "ec2:CreateTags",
        "ec2:DescribeVpcs",
        "ec2:DescribeVpcAttribute",
        "ec2:DescribeSubnets",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeAccountAttributes",
        "ec2:DescribeNetworkInterfaces"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": { "aws:RequestedRegion": "us-east-1" }
      }
    }
  ]
}
```

`ec2:DescribeNetworkInterfaces` in particular only surfaces on `terraform destroy`: the AWS
provider checks a security group for attached ENIs before deleting it, even when (as here)
nothing is actually still attached by that point in the destroy sequence.

## What's deliberately NOT here

- **The default VPC(Virtual Private Cloud)/subnets/security group** - referenced via `data` sources
  (`data.tf`), not created. This project intentionally uses the account's existing
  default VPC rather than building dedicated networking.
- **Database-level objects** - the `analytics` schema, its tables/views, grants, and the
  `looker_reader` database user are in-database SQL objects, not AWS resources. They're
  managed by the pipeline code (`oil_pipeline.load.redshift`) and one-time setup SQL, not
  Terraform.
- **The local dev IAM user** (`pipeline-gcp-to-aws-migration`) and its permissions -
  this is the bootstrap identity Terraform itself runs as, so it's a manual prerequisite instead 
  (see account setup notes elsewhere in the repo).

## Usage

```
terraform init
terraform plan   # should show no changes if nothing's drifted
```

Only run `terraform apply` after reviewing the plan - most changes here touch real,
billed AWS resources (Redshift Serverless compute, in particular).

## Cost note

Redshift Serverless (`redshift.tf`) is the one cost-relevant resource - base capacity is
pinned to 4 RPU (the current AWS minimum), billed per-second only while actively
processing queries. Think carefully before raising `base_capacity`.

## Tearing down

`terraform destroy` removes everything Terraform manages here. Before running it:

1. If you want to keep the Looker Studio report working afterward, convert its data
   sources to Looker Studio's "Extract Data" snapshot first (freezes the report's data
   independently of Redshift - see the repo's project notes on this).
2. `terraform destroy` does not touch the database-level objects listed above - they
   disappear along with the namespace/workgroup automatically, nothing extra to clean up
   there.
