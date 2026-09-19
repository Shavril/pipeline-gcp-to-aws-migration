"""Load Parquet data from GCS into BigQuery, and run arbitrary BigQuery SQL/DDL."""

import logging

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def load_parquet_to_bigquery(gcs_uri: str, project: str, dataset: str, table: str) -> int:
    """Load a Parquet file from GCS into a BigQuery table.

    The table is replaced wholesale (WRITE_TRUNCATE) — this is a full
    reload, not an incremental upsert. The dataset must already exist.

    Returns the row count of the loaded table (already fetched here to log
    it, so the caller gets it for free rather than issuing a second query).
    """
    client = bigquery.Client(project=project)
    table_ref = f"{project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    load_job = client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    load_job.result()

    destination = client.get_table(table_ref)
    logger.info("Loaded %s rows into %s from %s", f"{destination.num_rows:,}", table_ref, gcs_uri)
    return destination.num_rows


def run_bigquery_sql(sql: str, project: str) -> None:
    """Execute an arbitrary SQL statement (e.g. CREATE OR REPLACE TABLE ... AS SELECT) against BigQuery."""
    client = bigquery.Client(project=project)
    job = client.query(sql)
    job.result()
    logger.info("Executed BigQuery SQL (job %s)", job.job_id)
