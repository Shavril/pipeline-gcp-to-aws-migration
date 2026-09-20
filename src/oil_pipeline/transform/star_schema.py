"""Redshift star-schema (fact/dimension) table definitions for the analytics warehouse.

TRUNCATE + INSERT INTO ... SELECT over the already-Redshift-resident
analytics tables (oil_production, wells, lease_operators, rrc_districts) --
materialized into a proper fact/dimension shape instead of an ad-hoc
join-at-query-time. transform/views.py's Looker-Studio-facing views read
these tables rather than the raw analytics tables directly (verified
byte-for-byte identical output against the pre-rewrite views before that
changeover shipped) -- this is the one place those joins/approximations are
computed. Nothing upstream of the warehouse (extract/transform/DuckDB/
Parquet/S3) needed to change to support any of it.

Model:
    fact_oil_production -- one row per lease per reporting month (same grain
        as the oil_production table it's built from). References dim_lease
        (lease_id) and dim_date (report_month).
    dim_lease -- one row per oil lease. References dim_district
        (district_code) and dim_operator (operator_number); also carries a
        lease-level county approximation for leases whose wells span more
        than one county (~5% of leases -- same MIN-per-lease approximation
        already used in transform/views.py's LEASE_COUNTY_CTE).
    dim_well -- one row per oil well, references dim_lease (lease_id). Not a
        dimension of fact_oil_production (production is reported at lease
        grain, not well grain) -- it hangs off dim_lease for well-level
        drill-down.
    dim_operator, dim_district, dim_date -- conformed dimensions.

Key strategy: dimension keys are the existing natural/business keys
(lease_id, api_number, operator_number, district_code, report_month), not
fabricated surrogate integers. None of these dimensions need slowly-changing-
dimension history -- the pipeline always reloads current state wholesale --
and Redshift's columnar storage doesn't get the join-performance benefit a
row-store warehouse gets from small-int surrogate keys, so a surrogate key
here would just be a layer of indirection with nothing to justify it.

district_code/operator_number are modeled as attributes of dim_lease (an
outrigger onto dim_district/dim_operator) rather than as direct dimensions of
fact_oil_production, because a lease has exactly one district and one current
operator -- that's baked into the lease's own natural key and P-4 record, not
a fact of the production report itself. Joining district/operator through
dim_lease avoids duplicating a lease-level attribute onto every one of its
monthly fact rows.
"""

DIM_DATE_QUERY = """SELECT DISTINCT
  report_month,
  CAST(EXTRACT(YEAR FROM report_month) AS INTEGER) AS year,
  CAST(EXTRACT(QUARTER FROM report_month) AS INTEGER) AS quarter,
  CAST(EXTRACT(MONTH FROM report_month) AS INTEGER) AS month,
  TRIM(TO_CHAR(report_month, 'Month')) AS month_name
FROM {oil_production_table}"""

DIM_DISTRICT_QUERY = """SELECT
  district_code,
  rrc_district_id,
  district_name
FROM {districts_table}"""

DIM_OPERATOR_QUERY = """SELECT DISTINCT
  operator_number,
  organization_name,
  p5_status
FROM {lease_operators_table}
WHERE operator_number IS NOT NULL"""

DIM_LEASE_QUERY = """WITH lease_county AS (
  SELECT lease_id, MIN(county_code) AS county_code
  FROM {wells_table}
  WHERE county_code IS NOT NULL
  GROUP BY lease_id
)
SELECT
  lo.lease_id,
  lo.district_code,
  lo.lease_nbr,
  lo.operator_number,
  lc.county_code
FROM {lease_operators_table} lo
LEFT JOIN lease_county lc ON lo.lease_id = lc.lease_id"""

DIM_WELL_QUERY = """SELECT
  api_number,
  lease_id,
  district_code,
  well_nbr,
  is_active,
  county_code,
  latitude,
  longitude,
  orig_compl_year,
  total_depth_ft,
  is_plugged,
  water_land_code
FROM {wells_table}"""

FACT_OIL_PRODUCTION_QUERY = """SELECT
  district_code || '-' || lease_nbr AS lease_id,
  report_month,
  oil_production_bbl,
  casinghead_gas_mcf,
  casinghead_gas_lift_mcf,
  oil_allowable_cycle_bbls,
  present_oil_status_bbl AS cumulative_overproduction_bbl,
  is_corrected_report,
  is_filed_by_edi
FROM {oil_production_table}"""

# Maps each star-schema table name to the query that builds it -- the single
# place that wires a table name to its definition, same pattern as
# transform.views.VIEW_DEFINITIONS.
STAR_SCHEMA_DEFINITIONS = {
    "dim_date": DIM_DATE_QUERY,
    "dim_district": DIM_DISTRICT_QUERY,
    "dim_operator": DIM_OPERATOR_QUERY,
    "dim_lease": DIM_LEASE_QUERY,
    "dim_well": DIM_WELL_QUERY,
    "fact_oil_production": FACT_OIL_PRODUCTION_QUERY,
}


def build_star_schema_table_sql(
    schema: str,
    table_name: str,
    oil_production_table: str = "oil_production",
    wells_table: str = "wells",
    lease_operators_table: str = "lease_operators",
    districts_table: str = "rrc_districts",
) -> str:
    """Build TRUNCATE + INSERT INTO ... SELECT statements for one of STAR_SCHEMA_DEFINITIONS.

    Not DROP + CREATE: transform/views.py's Looker Studio-facing views are
    built on top of these tables, and Redshift refuses to DROP a table that
    a view depends on ("cannot drop table ... because other objects depend
    on it"). TRUNCATE + INSERT preserves the table's identity, so
    dependent views keep working across every refresh. The table must
    already exist with a matching column list -- see load/redshift.py's
    ensure_star_schema_tables, called by every asset in star_schema_assets.py
    before this SQL runs.
    """
    query = STAR_SCHEMA_DEFINITIONS[table_name].format(
        oil_production_table=f"{schema}.{oil_production_table}",
        wells_table=f"{schema}.{wells_table}",
        lease_operators_table=f"{schema}.{lease_operators_table}",
        districts_table=f"{schema}.{districts_table}",
    )
    qualified_table = f"{schema}.{table_name}"
    return f"TRUNCATE TABLE {qualified_table};\nINSERT INTO {qualified_table}\n{query}"
