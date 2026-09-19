import pandas as pd
import pytest

from oil_pipeline.validation.core import ValidationError
from oil_pipeline.validation.transformed import (
    validate_lease_operators,
    validate_oil_production,
    validate_wells,
)


def _oil_production_df(**overrides):
    df = pd.DataFrame(
        {
            "district_code": ["01", "02"],
            "lease_nbr": ["000001", "000002"],
            "report_month": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "oil_production_bbl": [100, 200],
            "casinghead_gas_mcf": [5, 10],
            "rrc_district_id": ["1", "2"],
        }
    )
    for col, values in overrides.items():
        df[col] = values
    return df


def test_oil_production_valid_passes():
    result = validate_oil_production(_oil_production_df())
    assert len(result) == 2


def test_oil_production_duplicate_grain_raises():
    df = _oil_production_df(district_code=["01", "01"], lease_nbr=["000001", "000001"])
    with pytest.raises(ValidationError):
        validate_oil_production(df)


def test_oil_production_unmapped_district_warns_not_raises():
    df = _oil_production_df(rrc_district_id=["1", None])
    result = validate_oil_production(df)  # must not raise
    assert len(result) == 2


def _lease_operators_df(**overrides):
    df = pd.DataFrame(
        {
            "district_code": ["01", "02", "03"],
            "lease_nbr": ["000001", "000002", "000003"],
            "lease_id": ["01-000001", "02-000002", "03-000003"],
            "operator_number": ["111111", "222222", "333333"],
            "organization_name": ["Acme Oil", "Widget Energy", "Test Co"],
        }
    )
    for col, values in overrides.items():
        df[col] = values
    return df


def test_lease_operators_valid_passes():
    result = validate_lease_operators(_lease_operators_df())
    assert len(result) == 3


def test_lease_operators_duplicate_grain_raises():
    df = _lease_operators_df(district_code=["01", "01", "03"], lease_nbr=["000001", "000001", "000003"])
    with pytest.raises(ValidationError):
        validate_lease_operators(df)


def test_lease_operators_high_null_organization_rate_warns_not_raises():
    df = _lease_operators_df(organization_name=[None, None, "Test Co"])
    result = validate_lease_operators(df)  # must not raise
    assert len(result) == 3


def _wells_df(**overrides):
    df = pd.DataFrame(
        {
            "api_number": ["42012345", "42067890"],
            "lease_id": ["08-00001", "08-00002"],
            "total_depth_ft": [8500.0, 9000.0],
            "orig_compl_year": [1998.0, 2005.0],
            "latitude": [31.5, 32.0],
            "longitude": [-101.2, -100.5],
        }
    )
    for col, values in overrides.items():
        df[col] = values
    return df


def test_wells_valid_passes():
    result = validate_wells(_wells_df())
    assert len(result) == 2


def test_wells_duplicate_api_number_raises():
    df = _wells_df(api_number=["42012345", "42012345"])
    with pytest.raises(ValidationError):
        validate_wells(df)


def test_wells_total_depth_out_of_range_raises():
    df = _wells_df(total_depth_ft=[45000.0, 9000.0])  # exceeds the 40,000 ft ceiling
    with pytest.raises(ValidationError):
        validate_wells(df)


def test_wells_latitude_outside_texas_warns_not_raises():
    df = _wells_df(latitude=[45.0, 32.0])  # outside Texas's bounding box
    result = validate_wells(df)  # must not raise
    assert len(result) == 2
