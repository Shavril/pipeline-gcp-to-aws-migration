"""Looker Studio-facing Redshift view definitions.

Each view selects from its own source table ({table} -- fact_oil_production
or dim_well) joined to the star-schema dimensions (dim_lease, dim_district,
dim_operator) built in oil_pipeline.transform.star_schema, rather than
re-deriving lease_id/county/district lookups inline against the raw
analytics tables. The star schema is the single place those joins and
approximations (e.g. dim_lease.county_code's MIN-per-lease pick when a
lease's wells span more than one county) are computed; these views just
consume it, so it isn't computed twice.

Because of this, these views now depend on the star-schema tables being
built first -- see dagster_defs.definitions.analytics_views_job, which
includes the star-schema assets in its selection for exactly that reason.
"""

OIL_PRODUCTION_VIOLATIONS_VIEW_QUERY = """SELECT
  f.lease_id,
  dd.rrc_district_id,
  dd.district_name,
  dl.operator_number,
  op.organization_name,
  dl.county_code,
  '48' || dl.county_code AS county_fips,
  f.report_month,
  f.oil_production_bbl,
  f.oil_allowable_cycle_bbls,
  f.cumulative_overproduction_bbl,
  f.oil_production_bbl::FLOAT / NULLIF(f.oil_allowable_cycle_bbls, 0) AS allowable_utilization_ratio
FROM {table} f
LEFT JOIN {dim_lease_table} dl ON f.lease_id = dl.lease_id
LEFT JOIN {dim_district_table} dd ON dl.district_code = dd.district_code
LEFT JOIN {dim_operator_table} op ON dl.operator_number = op.operator_number
WHERE f.cumulative_overproduction_bbl > 0
ORDER BY f.cumulative_overproduction_bbl DESC"""

TOTAL_OIL_PRODUCTION_BY_LEASE_ID_VIEW_QUERY = """SELECT
  f.lease_id,
  dl.district_code,
  dd.district_name,
  dl.operator_number,
  op.organization_name,
  dl.county_code,
  '48' || dl.county_code AS county_fips,
  SUM(f.oil_production_bbl) AS total_oil_production_bbl
FROM {table} f
LEFT JOIN {dim_lease_table} dl ON f.lease_id = dl.lease_id
LEFT JOIN {dim_district_table} dd ON dl.district_code = dd.district_code
LEFT JOIN {dim_operator_table} op ON dl.operator_number = op.operator_number
GROUP BY f.lease_id, dl.district_code, dd.district_name, dl.operator_number, op.organization_name, dl.county_code
ORDER BY f.lease_id, dl.district_code ASC"""

TOTAL_OIL_PRODUCTION_BY_MONTH_AND_DISTRICT_CODE_VIEW_QUERY = """SELECT
  f.report_month,
  dl.district_code,
  dd.district_name,
  SUM(f.oil_production_bbl) AS total_oil_production_bbl
FROM {table} f
LEFT JOIN {dim_lease_table} dl ON f.lease_id = dl.lease_id
LEFT JOIN {dim_district_table} dd ON dl.district_code = dd.district_code
GROUP BY f.report_month, dl.district_code, dd.district_name
ORDER BY f.report_month, dl.district_code ASC"""

# Mirrors the by-month-and-district view above, grouped by county instead --
# county_fips is derived from dl.county_code the same way wells_view and
# total_oil_production_by_lease_id_view do it, so this is the county-grain
# counterpart of those. Kept at month grain (not pre-summed to an all-time
# total) so the Looker Studio county map can still be sliced by a date-range
# control, not just show one static lifetime total per county.
TOTAL_OIL_PRODUCTION_BY_MONTH_AND_COUNTY_VIEW_QUERY = """SELECT
  f.report_month,
  dl.county_code,
  '48' || dl.county_code AS county_fips,
  dl.district_code,
  dd.district_name,
  SUM(f.oil_production_bbl) AS total_oil_production_bbl
FROM {table} f
LEFT JOIN {dim_lease_table} dl ON f.lease_id = dl.lease_id
LEFT JOIN {dim_district_table} dd ON dl.district_code = dd.district_code
GROUP BY f.report_month, dl.county_code, dl.district_code, dd.district_name
ORDER BY f.report_month, dl.county_code ASC"""

# One generic, row-level view over `dim_well` (not pre-aggregated) --
# deliberately kept reusable rather than building one narrow view per chart.
# Every column needed for all 7 wells visualizations (map, county/district
# breakdown, wells-drilled-per-year, active/plugged split, depth
# distribution, wells-per-lease, land/water breakdown) is present at well
# grain; Looker Studio does the GROUP BY / histogram bucketing per-chart on
# top of this single view. county_fips uses the well's own county_code (not
# dim_lease's lease-level approximation) -- a well's county is exact, only a
# lease spanning wells in more than one county needs the approximation.
# district_code/district_name likewise come from the well's own
# district_code (dim_well, joined to dim_district directly), not through
# dim_lease -- ~0.02% of wells have no matching dim_lease row at all (the
# same lease_id match-rate quirk documented in transform/wells.py), and
# those wells still have their own district on record even without a
# lease/operator match. operator_number/organization_name have no such
# fallback -- they only exist via dim_lease -- so they're null for that
# same ~0.02%, same as before this view read the star schema.
WELLS_VIEW_QUERY = """SELECT
  dw.api_number,
  dw.lease_id,
  dw.district_code,
  dd.district_name,
  dl.operator_number,
  op.organization_name,
  dw.well_nbr,
  dw.county_code,
  '48' || dw.county_code AS county_fips,
  dw.latitude,
  dw.longitude,
  CASE WHEN dw.latitude IS NOT NULL AND dw.longitude IS NOT NULL
       THEN CAST(dw.latitude AS VARCHAR) || ',' || CAST(dw.longitude AS VARCHAR)
  END AS lat_long,
  dw.orig_compl_year,
  dw.total_depth_ft,
  dw.is_active,
  dw.is_plugged,
  dw.water_land_code
FROM {table} dw
LEFT JOIN {dim_district_table} dd ON dw.district_code = dd.district_code
LEFT JOIN {dim_lease_table} dl ON dw.lease_id = dl.lease_id
LEFT JOIN {dim_operator_table} op ON dl.operator_number = op.operator_number"""

# Maps each view name to its query template + the source table it reads
# from -- the single place that wires a view name to its definition.
VIEW_DEFINITIONS = {
    "oil_production_violations_view": {
        "query": OIL_PRODUCTION_VIOLATIONS_VIEW_QUERY,
        "source_table": "fact_oil_production",
    },
    "total_oil_production_by_lease_id_view": {
        "query": TOTAL_OIL_PRODUCTION_BY_LEASE_ID_VIEW_QUERY,
        "source_table": "fact_oil_production",
    },
    "total_oil_production_by_month_and_district_code_view": {
        "query": TOTAL_OIL_PRODUCTION_BY_MONTH_AND_DISTRICT_CODE_VIEW_QUERY,
        "source_table": "fact_oil_production",
    },
    "total_oil_production_by_month_and_county_view": {
        "query": TOTAL_OIL_PRODUCTION_BY_MONTH_AND_COUNTY_VIEW_QUERY,
        "source_table": "fact_oil_production",
    },
    "wells_view": {
        "query": WELLS_VIEW_QUERY,
        "source_table": "dim_well",
    },
}


def build_view_sql(
    schema: str,
    view_name: str,
    source_table: str | None = None,
    dim_lease_table: str = "dim_lease",
    dim_district_table: str = "dim_district",
    dim_operator_table: str = "dim_operator",
) -> str:
    """Build a CREATE OR REPLACE VIEW statement for one of the VIEW_DEFINITIONS.

    Redshift supports CREATE OR REPLACE VIEW directly (unlike tables), so
    this stays one statement.

    source_table defaults to the view's own definition (VIEW_DEFINITIONS[view_name]["source_table"])
    but can be overridden if ever needed (e.g. pointing at a differently-named table).
    """
    definition = VIEW_DEFINITIONS[view_name]
    if source_table is None:
        source_table = definition["source_table"]
    query = definition["query"].format(
        table=f"{schema}.{source_table}",
        dim_lease_table=f"{schema}.{dim_lease_table}",
        dim_district_table=f"{schema}.{dim_district_table}",
        dim_operator_table=f"{schema}.{dim_operator_table}",
    )
    return f"CREATE OR REPLACE VIEW {schema}.{view_name} AS\n{query}"
