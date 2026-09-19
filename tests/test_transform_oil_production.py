from pathlib import Path

import pandas as pd

from oil_pipeline.load.duckdb import save_tables
from oil_pipeline.transform.oil_production import build_oil_production


def _seed(db_path: Path, production: pd.DataFrame, cycle: pd.DataFrame) -> None:
    save_tables({"production": production, "cycle": cycle}, db_path)


def test_build_oil_production_joins_on_lease_and_cycle_key(tmp_path: Path):
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
    _seed(db_path, production, cycle)

    df = build_oil_production(db_path)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["report_month"] == pd.Timestamp("2024-01-01")
    assert row["oil_production_bbl"] == 100
    assert row["is_corrected_report"]
    assert not row["is_filed_by_edi"]
    assert row["rrc_district_id"] == "1"


def test_build_oil_production_drops_cycles_with_no_production(tmp_path: Path):
    # An inner join: idle/allowable-only cycles with no matching production
    # row must not appear (build_oil_production's documented grain).
    db_path = tmp_path / "test.duckdb"
    production = pd.DataFrame(
        {
            "district_code": ["01"],
            "lease_nbr": ["000001"],
            "rpt_cycle_key_yymm": ["2401"],
            "oil_production_bbl": [100],
            "casinghead_gas_mcf": [5],
            "casinghead_gas_lift_mcf": [0],
            "corrected_report_flag": ["N"],
            "filed_by_edi_flag": ["N"],
        }
    )
    cycle = pd.DataFrame(
        {
            "district_code": ["01", "01"],
            "lease_nbr": ["000001", "000001"],
            "rpt_cycle_key_yymm": ["2401", "2402"],  # 2402 has no matching production
            "oil_allowable_cycle_bbls": [200, 200],
            "present_oil_status_bbl": [50, 60],
        }
    )
    _seed(db_path, production, cycle)

    df = build_oil_production(db_path)

    assert len(df) == 1
    assert df.iloc[0]["report_month"] == pd.Timestamp("2024-01-01")


def test_build_oil_production_unmapped_district_code_yields_null_id(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    production = pd.DataFrame(
        {
            "district_code": ["99"],  # not in DISTRICT_ID_BY_CODE
            "lease_nbr": ["000001"],
            "rpt_cycle_key_yymm": ["2401"],
            "oil_production_bbl": [100],
            "casinghead_gas_mcf": [5],
            "casinghead_gas_lift_mcf": [0],
            "corrected_report_flag": ["N"],
            "filed_by_edi_flag": ["N"],
        }
    )
    cycle = pd.DataFrame(
        {
            "district_code": ["99"],
            "lease_nbr": ["000001"],
            "rpt_cycle_key_yymm": ["2401"],
            "oil_allowable_cycle_bbls": [200],
            "present_oil_status_bbl": [50],
        }
    )
    _seed(db_path, production, cycle)

    df = build_oil_production(db_path)

    assert pd.isna(df.iloc[0]["rrc_district_id"])
