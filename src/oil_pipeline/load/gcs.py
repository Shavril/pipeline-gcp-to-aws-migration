"""Upload local files to Google Cloud Storage."""

import logging
from pathlib import Path

from google.cloud import storage

logger = logging.getLogger(__name__)


def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str, project: str | None = None) -> None:
    """Upload a local file to a GCS bucket, overwriting any existing object at blob_name."""
    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    logger.info("Uploaded %s to gs://%s/%s", local_path, bucket_name, blob_name)
