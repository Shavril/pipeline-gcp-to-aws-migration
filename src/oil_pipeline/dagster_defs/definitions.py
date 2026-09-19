from dagster import AssetSelection, Definitions, define_asset_job, in_process_executor, load_assets_from_modules

from oil_pipeline.dagster_defs import assets, star_schema_assets, view_assets
from oil_pipeline.dagster_defs.star_schema_assets import (
    dim_date,
    dim_district,
    dim_lease,
    dim_operator,
    dim_well,
    fact_oil_production,
)
from oil_pipeline.dagster_defs.view_assets import (
    oil_production_violations_view,
    total_oil_production_by_lease_id_view,
    total_oil_production_by_month_and_county_view,
    total_oil_production_by_month_and_district_code_view,
    wells_view,
)

# Dagster's default multiprocess executor deadlocks on Windows for this
# pipeline: its compute-log capture (poll_compute_logs.py) hangs waiting on
# the spawned step subprocess. in_process_executor runs every step in a
# single process instead, sidestepping it -- fine at this pipeline's scale.

# view_assets.py's assets just (re-)define BigQuery views -- since a view is
# a saved query evaluated fresh at query time (not a materialized
# snapshot), they only need to run again when their SQL changes, not on
# every routine data refresh. Excluded from data_refresh_job; use
# analytics_views_job to (re-)create them on demand. If you add another
# view asset to view_assets.py, add it to view_asset_selection below too.
view_asset_selection = AssetSelection.assets(
    oil_production_violations_view,
    total_oil_production_by_lease_id_view,
    total_oil_production_by_month_and_district_code_view,
    total_oil_production_by_month_and_county_view,
    wells_view,
)

# star_schema_assets.py's fact/dimension tables are also (re-)built on demand
# via star_schema_job, not on every routine data refresh -- same reasoning as
# the views above. If you add another asset to star_schema_assets.py, add it
# to star_schema_asset_selection below too.
star_schema_asset_selection = AssetSelection.assets(
    dim_date,
    dim_district,
    dim_operator,
    dim_lease,
    dim_well,
    fact_oil_production,
)

data_refresh_job = define_asset_job(
    "data_refresh_job",
    selection=AssetSelection.all() - view_asset_selection - star_schema_asset_selection,
    executor_def=in_process_executor,
)

# The views now read the star schema (transform/views.py), not the raw
# analytics tables directly -- so analytics_views_job's selection includes
# star_schema_asset_selection too, not just the views. Dagster orders
# execution within the job from the asset graph itself (star schema before
# views, since the views declare deps on it), so this stays one command for
# a complete, correct refresh of both layers.
analytics_views_job = define_asset_job(
    "analytics_views_job",
    selection=view_asset_selection | star_schema_asset_selection,
    executor_def=in_process_executor,
)

star_schema_job = define_asset_job(
    "star_schema_job",
    selection=star_schema_asset_selection,
    executor_def=in_process_executor,
)

defs = Definitions(
    assets=load_assets_from_modules([assets, view_assets, star_schema_assets]),
    jobs=[data_refresh_job, analytics_views_job, star_schema_job],
)
