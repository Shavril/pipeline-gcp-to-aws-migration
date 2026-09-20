"""Load Parquet data from S3 into Redshift Serverless, and run arbitrary Redshift SQL/DDL.

Uses the Redshift Data API (boto3's redshift-data client):
authenticates via the standard AWS credential chain against the workgroup.
"""

import logging
import time

import boto3

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1.0

# Redshift's COPY command loads into an already-existing table, and
# doesn't infer a schema from the source Parquet file.
# Columns/types below are derived from the DataFrames built by
# transform/oil_production.py, transform/lease_operators.py, and
# transform/wells.py.
_RAW_TABLE_DDL = {
    "oil_production": """
        CREATE TABLE IF NOT EXISTS {schema}.oil_production (
            district_code VARCHAR(8),
            lease_nbr VARCHAR(16),
            report_month DATE,
            oil_production_bbl BIGINT,
            casinghead_gas_mcf BIGINT,
            casinghead_gas_lift_mcf BIGINT,
            oil_allowable_cycle_bbls BIGINT,
            present_oil_status_bbl BIGINT,
            is_corrected_report BOOLEAN,
            is_filed_by_edi BOOLEAN,
            rrc_district_id VARCHAR(8)
        )
    """,
    "lease_operators": """
        CREATE TABLE IF NOT EXISTS {schema}.lease_operators (
            district_code VARCHAR(8),
            lease_nbr VARCHAR(16),
            lease_id VARCHAR(32),
            operator_number VARCHAR(16),
            organization_name VARCHAR(256),
            p5_status VARCHAR(16)
        )
    """,
    "wells": """
        CREATE TABLE IF NOT EXISTS {schema}.wells (
            api_number VARCHAR(32),
            district_code VARCHAR(8),
            lease_nbr VARCHAR(16),
            lease_id VARCHAR(32),
            well_nbr VARCHAR(16),
            is_active BOOLEAN,
            county_code VARCHAR(8),
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            orig_compl_year INTEGER,
            total_depth_ft INTEGER,
            is_plugged BOOLEAN,
            water_land_code VARCHAR(8)
        )
    """,
}


def _wait_for_statement(client, statement_id: str) -> None:
    """Poll a Redshift Data API statement until it finishes; raise if it failed."""
    while True:
        response = client.describe_statement(Id=statement_id)
        status = response["Status"]
        if status == "FINISHED":
            return
        if status in ("FAILED", "ABORTED"):
            raise RuntimeError(f"Redshift statement {status}: {response.get('Error')}")
        time.sleep(_POLL_INTERVAL_SECONDS)


def run_redshift_sql(sql: str, workgroup: str, database: str) -> None:
    """Execute an arbitrary SQL statement (DDL, CTAS, COPY, ...) against Redshift Serverless."""
    client = boto3.client("redshift-data")
    response = client.execute_statement(WorkgroupName=workgroup, Database=database, Sql=sql)
    _wait_for_statement(client, response["Id"])
    logger.info("Executed Redshift SQL (statement %s)", response["Id"])


def ensure_schema(workgroup: str, database: str, schema: str) -> None:
    """Create the schema if it doesn't already exist, and make it readable.

    Called from every entry point that creates a table/view in it.

    This is a single-user portfolio project, so tables/views are readable by
    any database user (the GRANT TO PUBLIC only reaches identities that can
    already authenticate into this AWS account/workgroup).

    Also sets a default-privileges rule:
    every table/view here is DROP + CREATE'd on refresh,
    so to each newly created table the permissions have to be assigned anew.
    """
    run_redshift_sql(
        f"""CREATE SCHEMA IF NOT EXISTS {schema};
GRANT USAGE ON SCHEMA {schema} TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO PUBLIC""",
        workgroup,
        database,
    )


def ensure_raw_tables(workgroup: str, database: str, schema: str) -> None:
    """Create the schema and raw analytics tables if they don't already exist."""
    ensure_schema(workgroup, database, schema)
    for ddl in _RAW_TABLE_DDL.values():
        run_redshift_sql(ddl.format(schema=schema), workgroup, database)


def load_parquet_to_redshift(
    s3_uri: str, workgroup: str, database: str, schema: str, table: str, iam_role_arn: str
) -> int:
    """Load a Parquet file from S3 into a Redshift table, replacing its contents wholesale.

    TRUNCATE + COPY, not an incremental upsert -- a full reload every run.

    Returns the row count of the loaded table (a follow-up SELECT COUNT(*)www.
    """
    ensure_raw_tables(workgroup, database, schema)

    client = boto3.client("redshift-data")
    qualified_table = f"{schema}.{table}"

    run_redshift_sql(f"TRUNCATE TABLE {qualified_table}", workgroup, database)
    run_redshift_sql(
        f"COPY {qualified_table} FROM '{s3_uri}' IAM_ROLE '{iam_role_arn}' FORMAT AS PARQUET",
        workgroup,
        database,
    )

    count_response = client.execute_statement(
        WorkgroupName=workgroup, Database=database, Sql=f"SELECT COUNT(*) FROM {qualified_table}"
    )
    _wait_for_statement(client, count_response["Id"])
    result = client.get_statement_result(Id=count_response["Id"])
    row_count = int(result["Records"][0][0]["longValue"])

    logger.info("Loaded %s rows into %s from %s", f"{row_count:,}", qualified_table, s3_uri)
    return row_count
