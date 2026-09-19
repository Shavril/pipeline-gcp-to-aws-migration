"""Build the oil_production analytics table from the raw production DuckDB tables."""

from pathlib import Path

import duckdb
import pandas as pd

from oil_pipeline.transform.districts import DISTRICT_ID_BY_CODE


def build_oil_production(db_path: Path) -> pd.DataFrame:
    """Join production + cycle into one row per lease per reporting month.

    Grain: one row per (district_code, lease_nbr, report_month) — verified 1:1
    against the source tables (production has no duplicate lease-months, and
    an inner join drops cycles where no production was actually reported that
    month, e.g. idle/allowable-only cycles).

    report_month is parsed from the YYMM reporting-cycle key. Month is the
    finest time grain the source data has — RRC leases file one total
    production volume per month, not a daily breakdown.
    """
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute("""
            SELECT
                p.district_code,
                p.lease_nbr,
                MAKE_DATE(
                    2000 + CAST(SUBSTR(p.rpt_cycle_key_yymm, 1, 2) AS INTEGER),
                    CAST(SUBSTR(p.rpt_cycle_key_yymm, 3, 2) AS INTEGER),
                    1
                ) AS report_month,
                p.oil_production_bbl,
                p.casinghead_gas_mcf,
                p.casinghead_gas_lift_mcf,
                c.oil_allowable_cycle_bbls,
                c.present_oil_status_bbl,
                p.corrected_report_flag = 'Y' AS is_corrected_report,
                p.filed_by_edi_flag = 'Y' AS is_filed_by_edi
            FROM production p
            JOIN cycle c
              ON p.district_code = c.district_code
             AND p.lease_nbr = c.lease_nbr
             AND p.rpt_cycle_key_yymm = c.rpt_cycle_key_yymm
        """).fetchdf()

    df["rrc_district_id"] = df["district_code"].map(DISTRICT_ID_BY_CODE)
    return df
