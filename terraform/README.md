# Terraform: AWS infrastructure

Codifies the AWS resources this project's local pipeline depends on: S3 bucket, Redshift
Serverless namespace/workgroup, the IAM role Redshift uses to read S3, the security
group that lets Looker Studio's native connector reach Redshift, and the OIDC setup that
lets GitHub Actions deploy this Terraform config without any long-lived AWS credentials.

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

## GitHub Actions deployment

`iam_github_oidc.tf` sets up federated auth so `.github/workflows/deploy-terraform.yml`
can run `terraform init/plan/apply` with a short-lived AWS session token instead of a
stored access key. The workflow triggers only on `workflow_dispatch` (manual) - it never
runs automatically on push.

The deploy role gets the same permission set documented above under "Prerequisites",
since it runs the exact same `terraform apply` a human would.

**One-time setup after the first `terraform apply` creates the role:**
1. `terraform output github_actions_role_arn` to get the role's ARN.
2. In the GitHub repo: Settings > Secrets and variables > Actions > Variables tab.
3. Add repository variables `AWS_DEPLOY_ROLE_ARN` (the ARN from step 1) and `AWS_REGION`
   (`us-east-1`).
4. To deploy: Actions tab > "deploy-terraform" workflow > Run workflow.

Three `workflow_dispatch`-only workflows use this OIDC role - see "Tearing down" below for
the other two.

## Cost note

Two resources here cost real money - everything else (IAM roles, the OIDC provider, the
security group) is free to leave running indefinitely:

- **Redshift Serverless** (`redshift.tf`) is the dominant cost - base capacity is pinned
  to 4 RPU (the current AWS minimum, ~$0.375/RPU-hour in us-east-1), billed per-second only
  while actively processing queries. Think carefully before raising `base_capacity`.
- **S3** (`s3.tf`) costs $0.023/GB/month in us-east-1 for storage. At this project's data
  volume (tens of MB of Parquet output) that's a fraction of a cent per month - not zero,
  but roughly 2,000x cheaper per hour than Redshift while it's running. New AWS accounts
  also typically get 5 GB of S3 Standard free for the first 12 months.

## Tearing down

A blanket `terraform destroy` removes everything Terraform manages here - including the
OIDC provider and the deploy role that GitHub Actions itself authenticates with. That's a
real catch-22 if it's ever done through GitHub Actions: the workflow would delete its own
AWS access mid-run, and rebuilding afterward would need a human running `terraform apply`
locally again, the same way this project was originally bootstrapped.

IAM roles, the OIDC provider, and the security group cost nothing to leave running -
only Redshift Serverless and S3 cost real money (see "Cost note" above; Redshift is the
dominant cost by a wide margin, but S3 isn't literally free either). So routine cost pauses
should target only the costly resources, not do a full destroy. Two `workflow_dispatch`
workflows reflect this split:

- **`destroy-costly-resources`** - destroys the Redshift Serverless namespace/workgroup
  and the S3 bucket (`-target`; Terraform automatically includes the bucket's dependent
  encryption-config and public-access-block resources too). Safe to run whenever you want
  to pause spending; everything else, including the ability to rebuild via this same
  workflow later, stays intact. The bucket has `force_destroy = true`, so it deletes
  cleanly even with objects in it, and gets recreated automatically on the next
  `deploy-terraform` run.
- **`destroy-everything`** - full `terraform destroy`, including the OIDC role this
  workflow runs as. Requires typing `destroy everything` into the confirmation input.
  Use this only when actually done with the project - not for routine pauses.

Before either one, if you want to keep the Looker Studio report working afterward, convert
its data sources to Looker Studio's "Extract Data" snapshot first (freezes the report's
data independently of Redshift - see the repo's project notes on this). Neither destroy
touches the database-level objects listed above - they disappear along with the
namespace/workgroup automatically, nothing extra to clean up there.
