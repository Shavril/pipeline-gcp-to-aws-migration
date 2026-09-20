"""Star-schema (fact/dimension) Redshift table assets for the analytics warehouse.

Built on top of the already-materialized oil_production/wells/lease_operators/
rrc_districts Redshift tables -- same dependency pattern as view_assets.py,
but each asset here (re-)creates one fact/dimension table
(oil_pipeline.transform.star_schema) rather than a query-time view.
view_assets.py's views read these tables, not the raw analytics tables
directly, so this layer has to run first -- see
dagster_defs.definitions.analytics_views_job.

Like the views in view_assets.py, these are saved-query-evaluated-fresh
outputs, not part of the routine data-refresh flow -- see also
dagster_defs.definitions.star_schema_job, for refreshing the star schema on
its own.

Each asset reports its own build duration as MaterializeResult metadata --
see view_assets.py's module docstring for why no row-count query is added
on top of that here.
"""

import time

from dagster import MaterializeResult, asset

from oil_pipeline.config import get_settings
from oil_pipeline.dagster_defs.assets import (
    district_lookup_table,
    lease_operators_redshift,
    oil_production_redshift,
    wells_redshift,
)
from oil_pipeline.load.redshift import run_redshift_sql
from oil_pipeline.transform.star_schema import build_star_schema_table_sql

settings = get_settings()

REDSHIFT_WORKGROUP_NAME = settings.redshift_workgroup_name
REDSHIFT_DATABASE_NAME = settings.redshift_database_name
REDSHIFT_SCHEMA = settings.redshift_schema


@asset(
    group_name="redshift_star_schema",
    deps=[oil_production_redshift],
)
def dim_date() -> MaterializeResult:
    """Distinct report months from oil_production, with year/quarter/month attributes."""
    start = time.perf_counter()
    table_name = "dim_date"
    sql = build_star_schema_table_sql(REDSHIFT_SCHEMA, table_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{table_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_star_schema",
    deps=[district_lookup_table],
)
def dim_district() -> MaterializeResult:
    """District code/id/name reference, mirrored from rrc_districts for star-schema naming."""
    start = time.perf_counter()
    table_name = "dim_district"
    sql = build_star_schema_table_sql(REDSHIFT_SCHEMA, table_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{table_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_star_schema",
    deps=[lease_operators_redshift],
)
def dim_operator() -> MaterializeResult:
    """One row per operator_number, deduped from lease_operators."""
    start = time.perf_counter()
    table_name = "dim_operator"
    sql = build_star_schema_table_sql(REDSHIFT_SCHEMA, table_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{table_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_star_schema",
    deps=[lease_operators_redshift, wells_redshift],
)
def dim_lease() -> MaterializeResult:
    """One row per oil lease -- district, operator, and a lease-level county approximation."""
    start = time.perf_counter()
    table_name = "dim_lease"
    sql = build_star_schema_table_sql(REDSHIFT_SCHEMA, table_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{table_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_star_schema",
    deps=[wells_redshift],
)
def dim_well() -> MaterializeResult:
    """One row per oil well."""
    start = time.perf_counter()
    table_name = "dim_well"
    sql = build_star_schema_table_sql(REDSHIFT_SCHEMA, table_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{table_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})


@asset(
    group_name="redshift_star_schema",
    deps=[oil_production_redshift],
)
def fact_oil_production() -> MaterializeResult:
    """One row per lease per reporting month -- the production fact table."""
    start = time.perf_counter()
    table_name = "fact_oil_production"
    sql = build_star_schema_table_sql(REDSHIFT_SCHEMA, table_name)
    run_redshift_sql(sql, workgroup=REDSHIFT_WORKGROUP_NAME, database=REDSHIFT_DATABASE_NAME)
    print()
    print(f"Created {REDSHIFT_SCHEMA}.{table_name}")
    return MaterializeResult(metadata={"duration_seconds": round(time.perf_counter() - start, 2)})
