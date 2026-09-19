"""Build the wells analytics table from the raw Well Bore DuckDB tables."""

from pathlib import Path

import duckdb
import pandas as pd


def build_wells(db_path: Path) -> pd.DataFrame:
    """Join Well Bore Root + Completion + New Location into one row per oil well.

    Grain: one row per well (api_number), oil wells only (Completion also
    covers gas wells — filtered to oil_code = 'O' to match this project's
    scope everywhere else).

    Completion is a documented *recurring* segment — a well can have more
    than one completion record (777,471 oil completions but only 623,014
    distinct wells; see docs/data_wells.md and
    notebooks/04_explore_wells.ipynb). For 115,873 of those wells this
    reflects the same well having been on more than one lease over its
    life. Rather than guess which completion is "current" (Completion
    carries no date to determine recency), one completion per well is
    picked deterministically (lowest district_code/lease_nbr/well_nbr) —
    an arbitrary but reproducible choice. This only affects district/lease
    attribution for ~18.6% of oil wells; the district itself differs
    across a well's multiple completions in only 947 cases (0.15% of oil
    wells) per the exploration notebook, so this approximation is safe in
    the large majority of cases.

    New Location is non-recurring per the format spec and has essentially
    no duplicate api_numbers (1 out of 1,018,543) — deduped defensively
    anyway, same technique as Completion.

    lease_nbr is 5 digits on this tape vs. 6 digits on the production/P-4
    tapes (docs/data_wells.md) — zero-padded here so lease_id matches the
    convention used by oil_production/lease_operators (verified: 99.98%
    of oil completions match an existing lease_operators.lease_id after
    padding).

    total_depth is nulled out above 40,000 ft — deeper than any well ever
    drilled anywhere, confirmed as data-entry noise affecting only 8 of
    1,211,829 Root records. orig_compl_year is nulled out unless it falls
    in a plausible 1900-2026 range, filtering out found garbage values
    like '88' and '1200' (4 records total). latitude/longitude are nulled
    out when both are exactly 0 — an unset placeholder, not a real
    coordinate at 0°N 0°E (affects 6,898 of 1,018,543 New Location
    records per the exploration notebook).
    """
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute("""
            WITH completion_oil AS (
                SELECT
                    api_number,
                    district_code,
                    LPAD(lease_nbr, 6, '0') AS lease_nbr,
                    well_nbr,
                    active_inactive_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY api_number
                        ORDER BY district_code, lease_nbr, well_nbr
                    ) AS rn
                FROM wells_completion
                WHERE oil_code = 'O'
            ),
            completion_primary AS (
                SELECT api_number, district_code, lease_nbr, well_nbr, active_inactive_code
                FROM completion_oil
                WHERE rn = 1
            ),
            newloc_dedup AS (
                SELECT
                    api_number, loc_county, latitude, longitude,
                    ROW_NUMBER() OVER (PARTITION BY api_number ORDER BY loc_county) AS rn
                FROM wells_new_location
            )
            SELECT
                r.api_number,
                c.district_code,
                c.lease_nbr,
                CONCAT(c.district_code, '-', c.lease_nbr) AS lease_id,
                TRIM(c.well_nbr) AS well_nbr,
                c.active_inactive_code = 'A' AS is_active,
                COALESCE(n.loc_county, r.res_cnty_code) AS county_code,
                CASE WHEN n.latitude != 0 OR n.longitude != 0 THEN n.latitude END AS latitude,
                CASE WHEN n.latitude != 0 OR n.longitude != 0 THEN n.longitude END AS longitude,
                CASE
                    WHEN r.orig_compl_year != '0000'
                     AND CAST(r.orig_compl_year AS INTEGER) BETWEEN 1900 AND 2026
                    THEN CAST(r.orig_compl_year AS INTEGER)
                END AS orig_compl_year,
                CASE
                    WHEN CAST(r.total_depth AS INTEGER) BETWEEN 1 AND 40000
                    THEN CAST(r.total_depth AS INTEGER)
                END AS total_depth_ft,
                r.plug_flag = 'Y' AS is_plugged,
                r.water_land_code
            FROM wells_root r
            JOIN completion_primary c ON r.api_number = c.api_number
            LEFT JOIN newloc_dedup n ON r.api_number = n.api_number AND n.rn = 1
        """).fetchdf()

    return df
