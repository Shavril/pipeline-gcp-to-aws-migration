"""Data pipeline assets: extract/validate -> DuckDB -> transform/validate ->
Parquet -> S3 -> Redshift. (Analytics views live in view_assets.py, a
separate, growing file of Redshift-warehouse-facing view assets, kept apart
from this data-flow file to avoid clutter.)

Each asset's body is the pipeline logic itself (extract/validate, transform/
validate, save, upload, load), not a delegate call elsewhere. Dagster
supports invoking @asset-decorated functions as plain Python outside of a
run (arguments passed straight through, no execution context needed) --
tests/test_full_pipeline_smoke.py does exactly that, calling these same
functions directly against real infrastructure, so there's exactly one copy
of this logic exercised, not a second hand-maintained copy. (Each returns a
MaterializeResult rather than a plain value, so that test has to unwrap
`.value` at each call site it chains further -- see its `_unwrap` helper.
Dagster's own engine does this unwrapping automatically when the asset graph
runs normally; only calling these functions directly needs to do it by hand.)

Each asset attaches observability metadata (records read/written,
duplicates collapsed, validation warnings, duration) to its
MaterializeResult rather than only printing it to the console -- visible per
run in the Dagster UI's asset catalog, not just buried in a log stream. The
prints stay too, for anyone reading logs from a run without the UI open.

Each of the three pipeline lines (oil_production, lease_operators, wells)
has its own DuckDB file (oil_pipeline.config.Settings) instead of one
shared one -- DuckDB allows only one writer per file, and Dagster gives no
ordering guarantee between assets without a real data dependency (e.g.
production_raw/p4_raw/p5_raw/wells_raw have none between them). Splitting
the file per line removes that contention structurally, rather than
relying on a specific executor's scheduling behavior to avoid it.

p4_raw and p5_raw still share lease_operators_db_path (both feed
lease_operators, so there was no clean way to split further without a
cross-database ATTACH) -- they have no data dependency on each other
either, so in principle they could still race if the executor ever
changes. dagster_defs.definitions.data_refresh_job pins in_process_executor,
which runs steps one at a time regardless of the dependency graph
(verified empirically, not just assumed), which covers this today.
"""

import time
from pathlib import Path

import duckdb
import pandas as pd
from dagster import MaterializeResult, asset

from oil_pipeline.config import get_settings
from oil_pipeline.extract.p4_operators import load_p4f606
from oil_pipeline.extract.p5_organizations import load_orf850
from oil_pipeline.extract.production import load_pdf100
from oil_pipeline.extract.wells import load_dbf900
from oil_pipeline.load.duckdb import save_tables
from oil_pipeline.load.parquet import save_parquet
from oil_pipeline.load.redshift import ensure_schema, load_parquet_to_redshift, run_redshift_sql
from oil_pipeline.load.s3 import upload_to_s3
from oil_pipeline.transform.districts import DISTRICT_ID_BY_CODE, build_district_lookup_sql
from oil_pipeline.transform.lease_operators import build_lease_operators
from oil_pipeline.transform.oil_production import build_oil_production
from oil_pipeline.transform.wells import build_wells
from oil_pipeline.validation.raw import (
    validate_p4_raw,
    validate_p5_raw,
    validate_production_raw,
    validate_wells_raw,
)
from oil_pipeline.validation.transformed import (
    validate_lease_operators,
    validate_oil_production,
    validate_wells,
)

settings = get_settings()

RAW_DATA_PATH = settings.raw_production_path
P4_DATA_PATH = settings.raw_p4_path
P5_DATA_PATH = settings.raw_p5_path
WELLS_DATA_PATH = settings.raw_wells_path
OIL_PRODUCTION_DB_PATH = settings.oil_production_db_path
LEASE_OPERATORS_DB_PATH = settings.lease_operators_db_path
WELLS_DB_PATH = settings.wells_db_path
PROCESSED_DATA_PATH = settings.processed_data_path

AWS_REGION = settings.aws_region
S3_BUCKET_NAME = settings.s3_bucket_name

REDSHIFT_WORKGROUP_NAME = settings.redshift_workgroup_name
REDSHIFT_DATABASE_NAME = settings.redshift_database_name
REDSHIFT_SCHEMA = settings.redshift_schema
REDSHIFT_S3_ROLE_ARN = settings.redshift_s3_role_arn
REDSHIFT_LOOKER_READER_PASSWORD = settings.redshift_looker_reader_password


def _scalar_count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    """Run a SELECT COUNT(*) query and return the count.

    fetchone() is typed as returning `tuple | None` in general (a query
    could return zero rows), but COUNT(*) with no GROUP BY always returns
    exactly one row -- even against an empty table, it returns 0, not
    nothing. The assert documents that guarantee for mypy rather than
    silencing the check.
    """
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


@asset(
    group_name="raw",
)
def production_raw() -> MaterializeResult:
    """Load the oil production raw data from PDF100.ebc
    into DuckDB tables root/cycle/production/prev_production/key_counts
    """
    start = time.perf_counter()
    results = validate_production_raw(load_pdf100(RAW_DATA_PATH))

    print()
    print("Record type breakdown:")
    print(results["key_counts"].to_string(index=False))

    print()
    print(f"Root (leases):             {len(results['root']):,}")
    print(f"Reporting Cycle:           {len(results['cycle']):,}")
    print(f"Production:                {len(results['production']):,}")
    print(f"Previous Production Rpt:   {len(results['prev_production']):,}")

    save_tables(results, OIL_PRODUCTION_DB_PATH)
    print()
    print(f"Saved tables to {OIL_PRODUCTION_DB_PATH}")

    records = {
        "root": len(results["root"]),
        "cycle": len(results["cycle"]),
        "production": len(results["production"]),
        "prev_production": len(results["prev_production"]),
    }
    validation_warnings = sum(results[t].attrs.get("validation_warnings", 0) for t in ("root", "cycle", "production"))
    return MaterializeResult(
        value=OIL_PRODUCTION_DB_PATH,
        metadata={
            "records_read": records,
            # validate() never silently drops a row -- a hard-check failure
            # halts the run instead -- so records_written always equals
            # records_read when this asset succeeds at all.
            "records_written": records,
            "validation_warnings": validation_warnings,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="raw",
)
def p4_raw() -> MaterializeResult:
    """Load P-4 operator raw data from p4f606.ebc
    into DuckDB table p4_root
    """
    start = time.perf_counter()
    p4_results = validate_p4_raw(load_p4f606(P4_DATA_PATH))
    root = p4_results["root"]
    print()
    print(f"P4 Root (oil + gas leases): {len(root):,}")
    save_tables({"p4_root": root}, LEASE_OPERATORS_DB_PATH)
    print(f"Saved p4_root table to {LEASE_OPERATORS_DB_PATH}")

    # Same (oil_gas_code, district_code, lease_nbr) subset as the soft
    # validation check in validation/raw.py -- a real, if rare, tape quirk
    # (see docs/data_p4_operators.md Known Issues), not a decode bug.
    duplicates_detected = int(root.duplicated(subset=["oil_gas_code", "district_code", "lease_nbr"]).sum())
    return MaterializeResult(
        metadata={
            "records_read": len(root),
            "records_written": len(root),
            "duplicates_detected": duplicates_detected,
            "validation_warnings": root.attrs.get("validation_warnings", 0),
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )


@asset(
    group_name="raw",
)
def p5_raw() -> MaterializeResult:
    """Load P-5 organization raw data from orf850.ebc
    into DuckDB table p5_organizations
    """
    start = time.perf_counter()
    p5_results = validate_p5_raw(load_orf850(P5_DATA_PATH))
    organizations = p5_results["organizations"]
    print()
    print(f"P5 Organizations:           {len(organizations):,}")
    save_tables({"p5_organizations": organizations}, LEASE_OPERATORS_DB_PATH)
    print(f"Saved p5_organizations table to {LEASE_OPERATORS_DB_PATH}")

    duplicates_detected = int(organizations.duplicated(subset=["operator_number"]).sum())
    return MaterializeResult(
        metadata={
            "records_read": len(organizations),
            "records_written": len(organizations),
            "duplicates_detected": duplicates_detected,
            "validation_warnings": organizations.attrs.get("validation_warnings", 0),
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )


@asset(
    group_name="raw",
)
def wells_raw() -> MaterializeResult:
    """Load wells raw data from dbf900.ebc into
    DuckDB tables wells_root/wells_completion/wells_new_location
    """
    start = time.perf_counter()
    wells_results = validate_wells_raw(load_dbf900(WELLS_DATA_PATH))
    print()
    print(f"Wells Root:               {len(wells_results['root']):,}")
    print(f"Wells Completion:         {len(wells_results['completion']):,}")
    print(f"Wells New Location:       {len(wells_results['new_location']):,}")
    save_tables(
        {
            "wells_root": wells_results["root"],
            "wells_completion": wells_results["completion"],
            "wells_new_location": wells_results["new_location"],
        },
        WELLS_DB_PATH,
    )
    print(f"Saved wells_root, wells_completion, and wells_new_location tables to {WELLS_DB_PATH}")

    records = {
        "root": len(wells_results["root"]),
        "completion": len(wells_results["completion"]),
        "new_location": len(wells_results["new_location"]),
    }
    # Completion is a documented *recurring* segment (transform/wells.py) --
    # more than one completion record per well is expected, not itself a
    # data-quality issue, but still worth surfacing as a count.
    duplicate_completions = int(wells_results["completion"]["api_number"].duplicated().sum())
    validation_warnings = sum(
        wells_results[t].attrs.get("validation_warnings", 0) for t in ("root", "completion", "new_location")
    )
    return MaterializeResult(
        metadata={
            "records_read": records,
            "records_written": records,
            "duplicate_completions": duplicate_completions,
            "validation_warnings": validation_warnings,
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )


@asset(
    group_name="duck_db_analytics",
    deps=[production_raw],
)
def oil_production() -> MaterializeResult:
    """DuckDB table oil_production: one row per lease per reporting month."""
    start = time.perf_counter()
    df = validate_oil_production(build_oil_production(OIL_PRODUCTION_DB_PATH))
    print()
    print(f"oil_production: {len(df):,} rows")
    save_tables({"oil_production": df}, OIL_PRODUCTION_DB_PATH)
    print(f"Saved oil_production table to {OIL_PRODUCTION_DB_PATH}")

    with duckdb.connect(str(OIL_PRODUCTION_DB_PATH), read_only=True) as con:
        records_read = _scalar_count(con, "SELECT COUNT(*) FROM production")

    return MaterializeResult(
        value=df,
        metadata={
            # Equal to records_written exactly when the documented
            # production/cycle 1:1 join guarantee holds (transform/
            # oil_production.py) -- a mismatch here would mean that broke.
            "records_read": records_read,
            "records_written": len(df),
            "validation_warnings": df.attrs.get("validation_warnings", 0),
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="duck_db_analytics",
    deps=[p4_raw, p5_raw],
)
def lease_operators() -> MaterializeResult:
    """DuckDB table lease_operators: one row per oil lease."""
    start = time.perf_counter()
    df = validate_lease_operators(build_lease_operators(LEASE_OPERATORS_DB_PATH))
    print()
    print(f"lease_operators: {len(df):,} rows")
    save_tables({"lease_operators": df}, LEASE_OPERATORS_DB_PATH)
    print(f"Saved lease_operators table to {LEASE_OPERATORS_DB_PATH}")

    with duckdb.connect(str(LEASE_OPERATORS_DB_PATH), read_only=True) as con:
        records_read = _scalar_count(con, "SELECT COUNT(*) FROM p4_root WHERE oil_gas_code = 'O'")

    return MaterializeResult(
        value=df,
        metadata={
            "records_read": records_read,
            "records_written": len(df),
            # The gap is duplicate P-4 root records collapsed to lease grain
            # -- see transform/lease_operators.py's dedup.
            "duplicates_collapsed": records_read - len(df),
            "validation_warnings": df.attrs.get("validation_warnings", 0),
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="duck_db_analytics",
    deps=[wells_raw],
)
def wells() -> MaterializeResult:
    """DuckDB table wells: one row per oil well."""
    start = time.perf_counter()
    df = validate_wells(build_wells(WELLS_DB_PATH))
    print()
    print(f"wells: {len(df):,} rows")
    save_tables({"wells": df}, WELLS_DB_PATH)
    print(f"Saved wells table to {WELLS_DB_PATH}")

    with duckdb.connect(str(WELLS_DB_PATH), read_only=True) as con:
        records_read = _scalar_count(con, "SELECT COUNT(*) FROM wells_completion WHERE oil_code = 'O'")

    return MaterializeResult(
        value=df,
        metadata={
            "records_read": records_read,
            "records_written": len(df),
            # The gap is wells with more than one oil completion record
            # collapsed to one -- see transform/wells.py's dedup.
            "duplicates_collapsed": records_read - len(df),
            "validation_warnings": df.attrs.get("validation_warnings", 0),
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="parquet_local_files",
)
def oil_production_parquet(oil_production: pd.DataFrame) -> MaterializeResult:
    """Save analytics table locally as Parquet file"""
    start = time.perf_counter()
    paths = save_parquet({"oil_production": oil_production}, PROCESSED_DATA_PATH)
    print()
    print(f"Wrote oil_production -> {paths['oil_production']}")
    return MaterializeResult(
        value=paths["oil_production"],
        metadata={
            "records_written": len(oil_production),
            "file_size_bytes": paths["oil_production"].stat().st_size,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="parquet_local_files",
)
def lease_operators_parquet(lease_operators: pd.DataFrame) -> MaterializeResult:
    """Save analytics table locally as Parquet file"""
    start = time.perf_counter()
    paths = save_parquet({"lease_operators": lease_operators}, PROCESSED_DATA_PATH)
    print()
    print(f"Wrote lease_operators -> {paths['lease_operators']}")
    return MaterializeResult(
        value=paths["lease_operators"],
        metadata={
            "records_written": len(lease_operators),
            "file_size_bytes": paths["lease_operators"].stat().st_size,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="parquet_local_files",
)
def wells_parquet(wells: pd.DataFrame) -> MaterializeResult:
    """Save analytics table locally as Parquet file"""
    start = time.perf_counter()
    paths = save_parquet({"wells": wells}, PROCESSED_DATA_PATH)
    print()
    print(f"Wrote wells -> {paths['wells']}")
    return MaterializeResult(
        value=paths["wells"],
        metadata={
            "records_written": len(wells),
            "file_size_bytes": paths["wells"].stat().st_size,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="s3_cloud_storage",
)
def oil_production_s3(oil_production_parquet: Path) -> MaterializeResult:
    """Upload the Parquet file to S3"""
    start = time.perf_counter()
    key = "oil_production.parquet"
    upload_to_s3(oil_production_parquet, S3_BUCKET_NAME, key, region=AWS_REGION)
    s3_uri = f"s3://{S3_BUCKET_NAME}/{key}"
    print()
    print(f"Uploaded {oil_production_parquet} -> {s3_uri}")
    return MaterializeResult(
        value=s3_uri,
        metadata={
            "file_size_bytes": oil_production_parquet.stat().st_size,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="s3_cloud_storage",
)
def lease_operators_s3(lease_operators_parquet: Path) -> MaterializeResult:
    """Upload the Parquet file to S3"""
    start = time.perf_counter()
    key = "lease_operators.parquet"
    upload_to_s3(lease_operators_parquet, S3_BUCKET_NAME, key, region=AWS_REGION)
    s3_uri = f"s3://{S3_BUCKET_NAME}/{key}"
    print()
    print(f"Uploaded {lease_operators_parquet} -> {s3_uri}")
    return MaterializeResult(
        value=s3_uri,
        metadata={
            "file_size_bytes": lease_operators_parquet.stat().st_size,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="s3_cloud_storage",
)
def wells_s3(wells_parquet: Path) -> MaterializeResult:
    """Upload the Parquet file to S3"""
    start = time.perf_counter()
    key = "wells.parquet"
    upload_to_s3(wells_parquet, S3_BUCKET_NAME, key, region=AWS_REGION)
    s3_uri = f"s3://{S3_BUCKET_NAME}/{key}"
    print()
    print(f"Uploaded {wells_parquet} -> {s3_uri}")
    return MaterializeResult(
        value=s3_uri,
        metadata={
            "file_size_bytes": wells_parquet.stat().st_size,
            "duration_seconds": round(time.perf_counter() - start, 2),
        },
    )


@asset(
    group_name="redshift_imports",
)
def oil_production_redshift(oil_production_s3: str) -> MaterializeResult:
    """Loads the oil_production Parquet file from S3 into its Redshift table."""
    start = time.perf_counter()
    row_count = load_parquet_to_redshift(
        oil_production_s3,
        workgroup=REDSHIFT_WORKGROUP_NAME,
        database=REDSHIFT_DATABASE_NAME,
        schema=REDSHIFT_SCHEMA,
        table="oil_production",
        iam_role_arn=REDSHIFT_S3_ROLE_ARN,
        looker_reader_password=REDSHIFT_LOOKER_READER_PASSWORD,
    )
    print()
    print(f"Loaded {oil_production_s3} -> {REDSHIFT_SCHEMA}.oil_production")
    return MaterializeResult(
        metadata={
            "records_written": row_count,
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )


@asset(
    group_name="redshift_imports",
)
def lease_operators_redshift(lease_operators_s3: str) -> MaterializeResult:
    """Loads the lease_operators Parquet file from S3 into its Redshift table."""
    start = time.perf_counter()
    row_count = load_parquet_to_redshift(
        lease_operators_s3,
        workgroup=REDSHIFT_WORKGROUP_NAME,
        database=REDSHIFT_DATABASE_NAME,
        schema=REDSHIFT_SCHEMA,
        table="lease_operators",
        iam_role_arn=REDSHIFT_S3_ROLE_ARN,
        looker_reader_password=REDSHIFT_LOOKER_READER_PASSWORD,
    )
    print()
    print(f"Loaded {lease_operators_s3} -> {REDSHIFT_SCHEMA}.lease_operators")
    return MaterializeResult(
        metadata={
            "records_written": row_count,
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )


@asset(
    group_name="redshift_imports",
)
def wells_redshift(wells_s3: str) -> MaterializeResult:
    """Loads the wells Parquet file from S3 into its Redshift table."""
    start = time.perf_counter()
    row_count = load_parquet_to_redshift(
        wells_s3,
        workgroup=REDSHIFT_WORKGROUP_NAME,
        database=REDSHIFT_DATABASE_NAME,
        schema=REDSHIFT_SCHEMA,
        table="wells",
        iam_role_arn=REDSHIFT_S3_ROLE_ARN,
        looker_reader_password=REDSHIFT_LOOKER_READER_PASSWORD,
    )
    print()
    print(f"Loaded {wells_s3} -> {REDSHIFT_SCHEMA}.wells")
    return MaterializeResult(
        metadata={
            "records_written": row_count,
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )


@asset(
    group_name="redshift_imports",
)
def district_lookup_table() -> MaterializeResult:
    """Create/refresh the small static district code/id/name lookup table rrc_districts"""
    start = time.perf_counter()
    ensure_schema(
        workgroup=REDSHIFT_WORKGROUP_NAME,
        database=REDSHIFT_DATABASE_NAME,
        schema=REDSHIFT_SCHEMA,
        looker_reader_password=REDSHIFT_LOOKER_READER_PASSWORD,
    )
    sql = build_district_lookup_sql(REDSHIFT_SCHEMA)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.rrc_districts")
    return MaterializeResult(
        metadata={
            "records_written": len(DISTRICT_ID_BY_CODE),
            "duration_seconds": round(time.perf_counter() - start, 2),
        }
    )
