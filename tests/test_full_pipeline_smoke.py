"""Opt-in end-to-end smoke test: runs the real pipeline against the real raw
tapes and real AWS infrastructure, through the local -> S3 boundary.

This replaces what used to be main.py's plain-script entry point. That script
demonstrated the same thing every asset-decorated function in assets.py
already claims -- that they're plain, directly-callable Python, not tied to
Dagster's execution engine -- but as a hand-run script, nothing ever
verified that claim automatically. Making it a real (if expensive, opt-in)
test does.

Stops after the S3 upload: the BigQuery-loading assets are not functional
as of Phase 1 (BigQuery load jobs can't read s3:// URIs -- see the comment
above oil_production_bigquery in assets.py) and will be replaced by
Redshift-from-S3 loaders in Phase 2. This test will grow
back to a full district-lookup/star-schema/views run once that lands.

Skipped unless the real raw files exist and every setting loads (both
checked at collection time, not import time, so this file never breaks
collection just because .env is missing -- see the try/except below). Marked
`smoke` and excluded from the default run via pyproject.toml's addopts, so a
plain `pytest`/`uv run pytest` stays fast and needs neither the ~11 GB tapes
nor AWS access. Run it explicitly with `pytest -m smoke`.

Doesn't assert exact row counts anywhere -- the RRC re-publishes these tapes
on a real schedule (see README's "Getting the raw files"), so record counts
drift between runs by design, not by bug.
"""

import pytest

from oil_pipeline.config import get_settings

try:
    _settings = get_settings()
    _raw_files_exist = all(
        p.exists()
        for p in (
            _settings.raw_production_path,
            _settings.raw_p4_path,
            _settings.raw_p5_path,
            _settings.raw_wells_path,
        )
    )
except Exception:
    _raw_files_exist = False

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not _raw_files_exist,
        reason="requires the real RRC raw tape files and a fully configured .env -- see README's "
        "'Getting the raw files'",
    ),
]


def _unwrap(result):
    """MaterializeResult carries asset metadata alongside its value; Dagster's
    engine extracts .value automatically for downstream assets, but calling
    these functions directly, as this test does, needs to unwrap it by hand."""
    from dagster import MaterializeResult

    return result.value if isinstance(result, MaterializeResult) else result


def test_full_pipeline_runs_end_to_end_against_real_infrastructure():
    from oil_pipeline.dagster_defs.assets import (
        lease_operators,
        lease_operators_parquet,
        lease_operators_s3,
        oil_production,
        oil_production_parquet,
        oil_production_s3,
        p4_raw,
        p5_raw,
        production_raw,
        wells,
        wells_parquet,
        wells_raw,
        wells_s3,
    )

    # Load the four raw tapes into DuckDB
    production_raw()
    p4_raw()
    p5_raw()
    wells_raw()

    # Transform into analytics-ready tables
    oil_production_df = _unwrap(oil_production())
    lease_operators_df = _unwrap(lease_operators())
    wells_df = _unwrap(wells())
    assert len(oil_production_df) > 0
    assert len(lease_operators_df) > 0
    assert len(wells_df) > 0

    # Save as Parquet and upload to S3
    oil_production_parquet_path = _unwrap(oil_production_parquet(oil_production_df))
    lease_operators_parquet_path = _unwrap(lease_operators_parquet(lease_operators_df))
    wells_parquet_path = _unwrap(wells_parquet(wells_df))

    oil_production_s3_uri = _unwrap(oil_production_s3(oil_production_parquet_path))
    lease_operators_s3_uri = _unwrap(lease_operators_s3(lease_operators_parquet_path))
    wells_s3_uri = _unwrap(wells_s3(wells_parquet_path))
    assert oil_production_s3_uri.startswith("s3://")
    assert lease_operators_s3_uri.startswith("s3://")
    assert wells_s3_uri.startswith("s3://")

    # Phase 2 picks up here: load from S3 into Redshift,
    # then district lookup, star schema, and Looker Studio views.
