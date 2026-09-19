import pandas as pd
import pytest

from oil_pipeline.validation.core import ValidationError
from oil_pipeline.validation.raw import (
    validate_p4_raw,
    validate_p5_raw,
    validate_production_raw,
    validate_wells_raw,
)


def _production_tables(**overrides):
    tables = {
        "root": pd.DataFrame(
            {
                "oil_code": ["O", "O"],
                "district_code": ["01", "02"],
                "lease_nbr": ["000001", "000002"],
                "movable_balance_bbl": [10, 20],
                "beginning_oil_status_bbl": [10, 20],
                "beginning_csghd_status_mcf": [0, 0],
                "oldest_eom_balance_bbl": [10, 20],
            }
        ),
        "cycle": pd.DataFrame(
            {
                "district_code": ["01", "02"],
                "lease_nbr": ["000001", "000002"],
                "rpt_cycle_key_yymm": ["2401", "2401"],
            }
        ),
        "production": pd.DataFrame(
            {
                "district_code": ["01", "02"],
                "lease_nbr": ["000001", "000002"],
                "rpt_cycle_key_yymm": ["2401", "2401"],
                "oil_production_bbl": [100, 200],
                "casinghead_gas_mcf": [5, 10],
            }
        ),
        "prev_production": pd.DataFrame(),
        "key_counts": pd.DataFrame(),
    }
    tables.update(overrides)
    return tables


def test_production_raw_valid_passes():
    result = validate_production_raw(_production_tables())
    assert len(result["root"]) == 2


def test_production_raw_duplicate_lease_key_raises():
    tables = _production_tables()
    tables["root"] = pd.DataFrame(
        {
            "oil_code": ["O", "O"],
            "district_code": ["01", "01"],
            "lease_nbr": ["000001", "000001"],  # duplicate grain
            "movable_balance_bbl": [10, 20],
            "beginning_oil_status_bbl": [10, 20],
            "beginning_csghd_status_mcf": [0, 0],
            "oldest_eom_balance_bbl": [10, 20],
        }
    )
    with pytest.raises(ValidationError):
        validate_production_raw(tables)


def test_production_raw_unexpected_oil_code_warns_not_raises():
    tables = _production_tables()
    tables["root"] = pd.DataFrame(
        {
            "oil_code": ["G", "O"],  # unexpected, but soft
            "district_code": ["01", "02"],
            "lease_nbr": ["000001", "000002"],
            "movable_balance_bbl": [10, 20],
            "beginning_oil_status_bbl": [10, 20],
            "beginning_csghd_status_mcf": [0, 0],
            "oldest_eom_balance_bbl": [10, 20],
        }
    )
    result = validate_production_raw(tables)  # must not raise
    assert len(result["root"]) == 2


def test_production_raw_records_zero_validation_warnings_when_clean():
    # See assets.py's observability metadata (records_read/written,
    # validation_warnings) -- validate() piggybacks the soft-check count on
    # df.attrs rather than changing its return type.
    result = validate_production_raw(_production_tables())
    assert result["root"].attrs["validation_warnings"] == 0


def test_production_raw_records_nonzero_validation_warnings_on_soft_check():
    tables = _production_tables()
    tables["root"] = pd.DataFrame(
        {
            "oil_code": ["G", "O"],  # unexpected, but soft
            "district_code": ["01", "02"],
            "lease_nbr": ["000001", "000002"],
            "movable_balance_bbl": [10, 20],
            "beginning_oil_status_bbl": [10, 20],
            "beginning_csghd_status_mcf": [0, 0],
            "oldest_eom_balance_bbl": [10, 20],
        }
    )
    result = validate_production_raw(tables)

    assert result["root"].attrs["validation_warnings"] >= 1


def _p4_tables(**overrides):
    tables = {
        "root": pd.DataFrame(
            {
                "oil_gas_code": ["O", "G"],
                "district_code": ["01", "01"],
                "lease_nbr": ["000001", "000001"],  # same lease key, different code -- allowed
                "operator_number": ["123456", "654321"],
            }
        ),
        "key_counts": pd.DataFrame(),
    }
    tables.update(overrides)
    return tables


def test_p4_raw_valid_passes():
    result = validate_p4_raw(_p4_tables())
    assert len(result["root"]) == 2


def test_p4_raw_duplicate_root_record_warns_not_raises():
    # Real data: the tape can contain exact duplicate root records for the
    # same (oil_gas_code, district_code, lease_nbr) -- confirmed on real
    # data, not decode corruption, so this must not halt the pipeline.
    tables = _p4_tables()
    tables["root"] = pd.DataFrame(
        {
            "oil_gas_code": ["G", "G"],
            "district_code": ["08", "08"],
            "lease_nbr": ["003753", "003753"],
            "operator_number": ["685350", "685350"],
        }
    )
    result = validate_p4_raw(tables)  # must not raise
    assert len(result["root"]) == 2


def test_p4_raw_invalid_oil_gas_code_raises():
    tables = _p4_tables()
    tables["root"] = pd.DataFrame(
        {
            "oil_gas_code": ["X"],
            "district_code": ["01"],
            "lease_nbr": ["000001"],
            "operator_number": ["123456"],
        }
    )
    with pytest.raises(ValidationError):
        validate_p4_raw(tables)


def _p5_tables(**overrides):
    tables = {
        "organizations": pd.DataFrame(
            {
                "operator_number": ["111111", "222222"],
                "organization_name": ["Acme Oil", "Widget Energy"],
                "p5_status": ["A", "X"],  # 'X' undocumented but seen in real data
            }
        ),
        "key_counts": pd.DataFrame(),
    }
    tables.update(overrides)
    return tables


def test_p5_raw_undocumented_status_warns_not_raises():
    result = validate_p5_raw(_p5_tables())  # must not raise
    assert len(result["organizations"]) == 2


def test_p5_raw_entirely_novel_status_warns_not_raises():
    tables = _p5_tables()
    tables["organizations"] = pd.DataFrame(
        {
            "operator_number": ["111111"],
            "organization_name": ["Acme Oil"],
            "p5_status": ["Z"],  # not in the documented-or-observed set at all
        }
    )
    result = validate_p5_raw(tables)  # must not raise -- unknown single chars just warn
    assert len(result["organizations"]) == 1


def test_p5_raw_malformed_status_raises():
    tables = _p5_tables()
    tables["organizations"] = pd.DataFrame(
        {
            "operator_number": ["111111"],
            "organization_name": ["Acme Oil"],
            "p5_status": [""],  # blank -- structurally malformed, not just an unknown code
        }
    )
    with pytest.raises(ValidationError):
        validate_p5_raw(tables)


def _wells_tables(**overrides):
    tables = {
        "root": pd.DataFrame(
            {
                "api_number": ["42012345", "42067890"],
                "field_district": ["08", ""],
                "orig_compl_year": ["1998", "0000"],
                "total_depth": ["08500", "00000"],
            }
        ),
        "completion": pd.DataFrame(
            {
                "api_number": ["42012345", "42067890"],
                "district_code": ["08", "08"],
                "lease_nbr": ["00001", "00002"],
                "oil_code": ["O", "O"],
            }
        ),
        "new_location": pd.DataFrame(
            {
                "api_number": ["42012345", "42067890"],
                "latitude": [31.5, 0.0],
                "longitude": [-101.2, 0.0],
            }
        ),
        "key_counts": pd.DataFrame(),
    }
    tables.update(overrides)
    return tables


def test_wells_raw_valid_passes():
    result = validate_wells_raw(_wells_tables())
    assert len(result["root"]) == 2


def test_wells_raw_space_padded_total_depth_passes():
    # Real data: some records are right-justified/space-padded rather than
    # zero-padded (e.g. "    0" for a well with no recorded depth).
    tables = _wells_tables()
    tables["root"] = pd.DataFrame(
        {
            "api_number": ["42012345"],
            "field_district": ["08"],
            "orig_compl_year": ["1998"],
            "total_depth": ["    0"],
        }
    )
    result = validate_wells_raw(tables)  # must not raise
    assert len(result["root"]) == 1


def test_wells_raw_non_numeric_total_depth_raises():
    tables = _wells_tables()
    tables["root"] = pd.DataFrame(
        {
            "api_number": ["42012345"],
            "field_district": ["08"],
            "orig_compl_year": ["1998"],
            "total_depth": ["ABCDE"],
        }
    )
    with pytest.raises(ValidationError):
        validate_wells_raw(tables)


def test_wells_raw_bad_api_number_length_raises():
    tables = _wells_tables()
    tables["root"] = pd.DataFrame(
        {
            "api_number": ["4201234"],  # 7 chars, should be 8
            "field_district": ["08"],
            "orig_compl_year": ["1998"],
            "total_depth": ["08500"],
        }
    )
    with pytest.raises(ValidationError):
        validate_wells_raw(tables)
