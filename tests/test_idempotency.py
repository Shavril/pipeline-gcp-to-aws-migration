"""Idempotency/determinism tests -- see README's "Pipeline properties".

Every transform here is a pure function of its input (no current-time,
random, or external state), and every write in load/ is a full replace --
CREATE OR REPLACE (DuckDB), DROP + CREATE / TRUNCATE + COPY (Redshift), or
overwrite-by-fixed-name (Parquet, S3) -- never an append. So running any
stage twice on the same input must produce exactly the same output, not
duplicates. These tests assert that directly rather than leaving it implicit
in the load/*.py docstrings.
"""

from pathlib import Path

import duckdb
import pandas as pd

from oil_pipeline.load.duckdb import save_tables
from oil_pipeline.load.parquet import save_parquet
from oil_pipeline.transform.lease_operators import build_lease_operators
from oil_pipeline.transform.oil_production import build_oil_production
from oil_pipeline.transform.star_schema import build_star_schema_table_sql
from oil_pipeline.transform.views import build_view_sql
from oil_pipeline.transform.wells import build_wells


def test_save_tables_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    table = pd.DataFrame({"api_number": ["1", "2", "3"]})

    save_tables({"wells": table}, db_path)
    save_tables({"wells": table}, db_path)  # same input, run again

    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute("SELECT api_number FROM wells ORDER BY api_number").fetchall()
    assert rows == [("1",), ("2",), ("3",)]  # still 3 rows, not 6


def test_save_parquet_is_idempotent(tmp_path: Path):
    processed_dir = tmp_path / "processed"
    table = pd.DataFrame({"api_number": ["1", "2"]})

    save_parquet({"wells": table}, processed_dir)
    save_parquet({"wells": table}, processed_dir)  # same input, run again

    result = pd.read_parquet(processed_dir / "wells.parquet")
    pd.testing.assert_frame_equal(result, table)  # still 2 rows, not 4


def test_build_oil_production_is_deterministic(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    production = pd.DataFrame(
        {
            "district_code": ["01"],
            "lease_nbr": ["000001"],
            "rpt_cycle_key_yymm": ["2401"],
            "oil_production_bbl": [100],
            "casinghead_gas_mcf": [5],
            "casinghead_gas_lift_mcf": [0],
            "corrected_report_flag": ["Y"],
            "filed_by_edi_flag": ["N"],
        }
    )
    cycle = pd.DataFrame(
        {
            "district_code": ["01"],
            "lease_nbr": ["000001"],
            "rpt_cycle_key_yymm": ["2401"],
            "oil_allowable_cycle_bbls": [200],
            "present_oil_status_bbl": [50],
        }
    )
    save_tables({"production": production, "cycle": cycle}, db_path)

    first = build_oil_production(db_path)
    second = build_oil_production(db_path)

    pd.testing.assert_frame_equal(first, second)


def test_build_wells_is_deterministic(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame(
        [
            {
                "api_number": "42012345",
                "field_district": "08",
                "res_cnty_code": "123",
                "orig_compl_year": "1998",
                "total_depth": "8500",
                "plug_flag": "N",
                "water_land_code": "L",
            }
        ]
    )
    completion = pd.DataFrame(
        [
            {
                "api_number": "42012345",
                "oil_code": "O",
                "district_code": "08",
                "lease_nbr": "00001",
                "well_nbr": "000001",
                "active_inactive_code": "A",
            }
        ]
    )
    new_location = pd.DataFrame(
        {
            "api_number": pd.Series([], dtype="string"),
            "loc_county": pd.Series([], dtype="string"),
            "latitude": pd.Series([], dtype="float64"),
            "longitude": pd.Series([], dtype="float64"),
        }
    )
    save_tables({"wells_root": root, "wells_completion": completion, "wells_new_location": new_location}, db_path)

    first = build_wells(db_path)
    second = build_wells(db_path)

    pd.testing.assert_frame_equal(first, second)


def test_build_lease_operators_is_deterministic(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    p4_root = pd.DataFrame(
        {
            "district_code": ["01"],
            "lease_nbr": ["000001"],
            "oil_gas_code": ["O"],
            "operator_number": ["111111"],
        }
    )
    p5_organizations = pd.DataFrame(
        {
            "operator_number": ["111111"],
            "organization_name": ["Acme Oil"],
            "p5_status": ["A"],
        }
    )
    save_tables({"p4_root": p4_root, "p5_organizations": p5_organizations}, db_path)

    first = build_lease_operators(db_path)
    second = build_lease_operators(db_path)

    pd.testing.assert_frame_equal(first, second)


def test_build_view_sql_is_deterministic():
    first = build_view_sql(schema="ds", view_name="wells_view")
    second = build_view_sql(schema="ds", view_name="wells_view")

    assert first == second


def test_build_star_schema_table_sql_is_deterministic():
    first = build_star_schema_table_sql(schema="ds", table_name="dim_lease")
    second = build_star_schema_table_sql(schema="ds", table_name="dim_lease")

    assert first == second
