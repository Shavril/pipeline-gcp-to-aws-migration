"""Upload local files to Amazon S3."""

import logging
from pathlib import Path

import boto3

logger = logging.getLogger(__name__)


def upload_to_s3(local_path: Path, bucket_name: str, key: str, region: str | None = None) -> None:
    """Upload a local file to an S3 bucket, overwriting any existing object at key.

    Credentials come from the standard boto3 chain (env vars, ~/.aws/credentials
    profile, etc.) -- never pass access keys explicitly.
    """
    client = boto3.client("s3", region_name=region)
    client.upload_file(str(local_path), bucket_name, key)
    logger.info("Uploaded %s to s3://%s/%s", local_path, bucket_name, key)
