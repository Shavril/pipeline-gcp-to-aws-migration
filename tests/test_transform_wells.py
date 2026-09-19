from pathlib import Path

import pandas as pd

from oil_pipeline.load.duckdb import save_tables
from oil_pipeline.transform.wells import build_wells


def _seed(db_path: Path, root: pd.DataFrame, completion: pd.DataFrame, new_location: pd.DataFrame) -> None:
    save_tables({"wells_root": root, "wells_completion": completion, "wells_new_location": new_location}, db_path)


def _empty_new_location() -> pd.DataFrame:
    # An empty object-dtype column has no values for DuckDB to infer a type
    # from and defaults to INTEGER -- the pandas "string" dtype carries its
    # own type metadata, so DuckDB maps it to VARCHAR even with zero rows.
    return pd.DataFrame(
        {
            "api_number": pd.Series([], dtype="string"),
            "loc_county": pd.Series([], dtype="string"),
            "latitude": pd.Series([], dtype="float64"),
            "longitude": pd.Series([], dtype="float64"),
        }
    )


def _root_row(**overrides):
    row = {
        "api_number": "42012345",
        "field_district": "08",
        "res_cnty_code": "123",
        "orig_compl_year": "1998",
        "total_depth": "8500",
        "plug_flag": "N",
        "water_land_code": "L",
    }
    row.update(overrides)
    return row


def test_build_wells_picks_lowest_completion_deterministically(tmp_path: Path):
    # A well with more than one oil completion (docs/data_wells.md: recurring
    # segment) picks the lowest (district_code, lease_nbr, well_nbr) -- not
    # the first or last row encountered.
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row()])
    completion = pd.DataFrame(
        [
            {
                "api_number": "42012345",
                "oil_code": "O",
                "district_code": "08",
                "lease_nbr": "00002",
                "well_nbr": "000001",
                "active_inactive_code": "A",
            },
            {
                "api_number": "42012345",
                "oil_code": "O",
                "district_code": "08",
                "lease_nbr": "00001",  # lower lease_nbr -- should win
                "well_nbr": "000001",
                "active_inactive_code": "I",
            },
        ]
    )
    new_location = _empty_new_location()
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert len(df) == 1
    assert df.iloc[0]["lease_nbr"] == "000001"  # zero-padded from "00001"
    assert not df.iloc[0]["is_active"]


def test_build_wells_pads_lease_nbr_to_six_digits(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row()])
    completion = pd.DataFrame(
        [
            {
                "api_number": "42012345",
                "oil_code": "O",
                "district_code": "08",
                "lease_nbr": "00042",
                "well_nbr": "000001",
                "active_inactive_code": "A",
            }
        ]
    )
    new_location = _empty_new_location()
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert df.iloc[0]["lease_nbr"] == "000042"
    assert df.iloc[0]["lease_id"] == "08-000042"


def test_build_wells_filters_gas_completions(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row()])
    completion = pd.DataFrame(
        [
            {
                "api_number": "42012345",
                "oil_code": "G",
                "district_code": "08",
                "lease_nbr": "00001",
                "well_nbr": "000001",
                "active_inactive_code": "A",
            }
        ]
    )
    new_location = _empty_new_location()
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert len(df) == 0


def test_build_wells_nulls_zero_zero_placeholder_coordinates(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row()])
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
    new_location = pd.DataFrame([{"api_number": "42012345", "loc_county": "123", "latitude": 0.0, "longitude": 0.0}])
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert pd.isna(df.iloc[0]["latitude"])
    assert pd.isna(df.iloc[0]["longitude"])


def test_build_wells_keeps_real_coordinate_at_zero_longitude(tmp_path: Path):
    # Only nulled when BOTH lat and long are exactly 0 -- a real coordinate
    # with one legitimate zero component must survive.
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row()])
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
    new_location = pd.DataFrame([{"api_number": "42012345", "loc_county": "123", "latitude": 31.5, "longitude": 0.0}])
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert df.iloc[0]["latitude"] == 31.5
    assert df.iloc[0]["longitude"] == 0.0


def test_build_wells_falls_back_to_root_county_without_new_location(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row(res_cnty_code="123")])
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
    new_location = _empty_new_location()
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert df.iloc[0]["county_code"] == "123"
    assert pd.isna(df.iloc[0]["latitude"])


def test_build_wells_nulls_implausible_total_depth_and_year(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame(
        [_root_row(total_depth="45000", orig_compl_year="0000")]  # both out of documented range
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
    new_location = _empty_new_location()
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert pd.isna(df.iloc[0]["total_depth_ft"])
    assert pd.isna(df.iloc[0]["orig_compl_year"])


def test_build_wells_keeps_plausible_total_depth_and_year(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    root = pd.DataFrame([_root_row(total_depth="8500", orig_compl_year="1998")])
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
    new_location = _empty_new_location()
    _seed(db_path, root, completion, new_location)

    df = build_wells(db_path)

    assert df.iloc[0]["total_depth_ft"] == 8500
    assert df.iloc[0]["orig_compl_year"] == 1998
