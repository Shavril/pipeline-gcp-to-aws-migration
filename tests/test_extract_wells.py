from pathlib import Path

from ebcdic_builders import pad, text_field, zoned_field

from oil_pipeline.extract.wells import (
    RECORD_LENGTH,
    load_dbf900,
    parse_completion,
    parse_new_location,
    parse_root,
)


def _root_record(
    api_prefix="420",
    api_suffix="12345",
    field_district="08",
    res_cnty_code="123",
    orig_compl_year="1998",
    orig_compl_month="05",
    orig_compl_day="01",
    total_depth="08500",
    plug_flag="N",
    water_land_code="L",
) -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("01", 2))
    pad(record, 2, text_field(api_prefix, 3))
    pad(record, 5, text_field(api_suffix, 5))
    pad(record, 14, text_field(field_district, 2))
    pad(record, 16, text_field(res_cnty_code, 3))
    pad(record, 20, text_field(orig_compl_year, 4))
    pad(record, 24, text_field(orig_compl_month, 2))
    pad(record, 26, text_field(orig_compl_day, 2))
    pad(record, 28, text_field(total_depth, 5))
    pad(record, 90, text_field(plug_flag, 1))
    pad(record, 131, text_field(water_land_code, 1))
    return bytes(record)


def _completion_record(
    oil_code="O", district_code="08", lease_nbr="00001", well_nbr="000001", active_inactive_code="A"
) -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("02", 2))
    pad(record, 2, text_field(oil_code, 1))
    pad(record, 3, text_field(district_code, 2))
    pad(record, 5, text_field(lease_nbr, 5))
    pad(record, 10, text_field(well_nbr, 6))
    pad(record, 45, text_field(active_inactive_code, 1))
    return bytes(record)


def _new_location_record(loc_county="123", latitude=31.5, longitude_magnitude=101.2) -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("13", 2))
    pad(record, 2, text_field(loc_county, 3))
    pad(record, 132, zoned_field(latitude, 10, decimal_places=7))
    # Longitude is stored as an unsigned magnitude (always positive sign
    # nibble) with an implicit West convention -- parse_new_location negates
    # it (docs/data_wells.md).
    pad(record, 142, zoned_field(longitude_magnitude, 10, decimal_places=7))
    return bytes(record)


def test_parse_root():
    row = parse_root(_root_record(api_prefix="420", api_suffix="12345"))
    assert row["api_number"] == "42012345"
    assert row["orig_compl_year"] == "1998"
    assert row["total_depth"] == "08500"


def test_parse_completion():
    row = parse_completion(_completion_record())
    assert row == {
        "oil_code": "O",
        "district_code": "08",
        "lease_nbr": "00001",
        "well_nbr": "000001",
        "active_inactive_code": "A",
    }


def test_parse_new_location_negates_longitude():
    row = parse_new_location(_new_location_record(latitude=31.5, longitude_magnitude=101.2))
    assert row["loc_county"] == "123"
    assert row["latitude"] == 31.5
    assert row["longitude"] == -101.2


def test_load_dbf900_stamps_api_number_onto_child_segments(tmp_path: Path):
    records = (
        _root_record(api_prefix="420", api_suffix="11111")
        + _completion_record(district_code="08", lease_nbr="00001")
        + _new_location_record(loc_county="123")
        + _root_record(api_prefix="420", api_suffix="22222")
        + _completion_record(district_code="09", lease_nbr="00002")
    )
    path = tmp_path / "dbf900.ebc"
    path.write_bytes(records)

    result = load_dbf900(path, progress_every=None)

    assert list(result["root"]["api_number"]) == ["42011111", "42022222"]
    assert list(result["completion"]["api_number"]) == ["42011111", "42022222"]
    assert list(result["new_location"]["api_number"]) == ["42011111"]
