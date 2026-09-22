"""Redshift-warehouse-facing view assets (Data Studio-facing, currently).

Kept separate from assets.py's data pipeline assets since this file is
expected to grow as more views/warehouse-side objects are added on top of
the data those assets load -- these aren't part of the raw->transform->
parquet->S3->Redshift data flow itself.

One asset per view in oil_pipeline.transform.views.VIEW_DEFINITIONS, each
deps-ing on exactly the star-schema tables its own SQL joins (not a blanket
dependency on every table) -- see each view's query in transform/views.py
for which tables that is. These views read the star schema
(star_schema_assets.py), not the raw analytics tables directly, so they
depend on that layer being built first -- see
dagster_defs.definitions.analytics_views_job.

Each asset reports its own build duration as MaterializeResult metadata --
no row-count query added on top of that (unlike assets.py's raw/transform
layer), since that would mean an extra Redshift query purely for
observability on every view refresh, and the interesting data-quality
signal (duplicates, validation warnings) already lives upstream, not in a
view that's just a join over already-validated tables.
"""

import time

from dagster import MaterializeResult, asset

from oil_pipeline.config import get_settings
from oil_pipeline.dagster_defs.star_schema_assets import dim_district, dim_lease, dim_operator, dim_well
from oil_pipeline.load.redshift import run_redshift_sql
from oil_pipeline.transform.views import build_view_sql

settings = get_settings()

REDSHIFT_WORKGROUP_NAME = settings.redshift_workgroup_name
REDSHIFT_DATABASE_NAME = settings.redshift_database_name
REDSHIFT_SCHEMA = settings.redshift_schema


@asset(
    group_name="redshift_views",
    deps=[dim_lease, dim_district, dim_operator],
)
def oil_production_violations_view() -> MaterializeResult:
    """Joins fact_oil_production, dim_lease, dim_district, dim_operator."""
    start = time.perf_counter()
    view_name = "oil_production_violations_view"
    sql = build_view_sql(REDSHIFT_SCHEMA, view_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{view_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_views",
    deps=[dim_lease, dim_district, dim_operator],
)
def total_oil_production_by_lease_id_view() -> MaterializeResult:
    """Joins fact_oil_production, dim_lease, dim_district, dim_operator."""
    start = time.perf_counter()
    view_name = "total_oil_production_by_lease_id_view"
    sql = build_view_sql(REDSHIFT_SCHEMA, view_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{view_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_views",
    deps=[dim_lease, dim_district],
)
def total_oil_production_by_month_and_district_code_view() -> MaterializeResult:
    """Joins fact_oil_production, dim_lease, dim_district."""
    start = time.perf_counter()
    view_name = "total_oil_production_by_month_and_district_code_view"
    sql = build_view_sql(REDSHIFT_SCHEMA, view_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{view_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_views",
    deps=[dim_lease, dim_district],
)
def total_oil_production_by_month_and_county_view() -> MaterializeResult:
    """Joins fact_oil_production, dim_lease, dim_district."""
    start = time.perf_counter()
    view_name = "total_oil_production_by_month_and_county_view"
    sql = build_view_sql(REDSHIFT_SCHEMA, view_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{view_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_views",
    deps=[dim_well, dim_lease, dim_district, dim_operator],
)
def wells_view() -> MaterializeResult:
    """Joins dim_well, dim_lease, dim_district, dim_operator."""
    start = time.perf_counter()
    view_name = "wells_view"
    sql = build_view_sql(REDSHIFT_SCHEMA, view_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{view_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})
