from pathlib import Path

from ebcdic_builders import comp3_field, pad, text_field

from oil_pipeline.extract.production import (
    RECORD_LENGTH,
    load_pdf100,
    parse_prev_production_report,
    parse_production,
    parse_reporting_cycle,
    parse_root,
)


def _root_record(oil_code="O", district_code="01", lease_nbr="000001") -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("01", 2))
    pad(record, 2, text_field(oil_code, 1))
    pad(record, 3, text_field(district_code, 2))
    pad(record, 5, text_field(lease_nbr, 6))
    pad(record, 11, comp3_field(10, 9))
    pad(record, 16, comp3_field(20, 9))
    pad(record, 21, comp3_field(0, 9))
    pad(record, 26, comp3_field(30, 9))
    return bytes(record)


def _cycle_record(rpt_cycle_key_yymm="2401") -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("02", 2))
    pad(record, 2, text_field(rpt_cycle_key_yymm, 4))
    return bytes(record)


def _production_record(oil_production_bbl=100, corrected="N") -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("03", 2))
    pad(record, 2, text_field(corrected, 1))
    pad(record, 6, comp3_field(oil_production_bbl, 9))
    pad(record, 11, comp3_field(5, 9))
    return bytes(record)


def test_parse_root():
    row = parse_root(_root_record())
    assert row == {
        "oil_code": "O",
        "district_code": "01",
        "lease_nbr": "000001",
        "movable_balance_bbl": 10,
        "beginning_oil_status_bbl": 20,
        "beginning_csghd_status_mcf": 0,
        "oldest_eom_balance_bbl": 30,
    }


def test_parse_reporting_cycle():
    row = parse_reporting_cycle(_cycle_record())
    assert row["rpt_cycle_key_yymm"] == "2401"


def test_parse_production():
    row = parse_production(_production_record())
    assert row["oil_production_bbl"] == 100
    assert row["corrected_report_flag"] == "N"


def test_parse_prev_production_report():
    record = bytearray(text_field(" ", 20))
    pad(record, 2, text_field("2024", 4))
    row = parse_prev_production_report(bytes(record))
    assert row["prev_posting_year"] == "2024"


def test_load_pdf100_stamps_lease_key_onto_child_segments(tmp_path: Path):
    """Root has no explicit foreign key -- cycle/production segments inherit
    (district_code, lease_nbr) positionally from the most recent Root, and
    production inherits rpt_cycle_key_yymm from the most recent Cycle."""
    records = (
        _root_record(district_code="01", lease_nbr="000001")
        + _cycle_record("2401")
        + _production_record(oil_production_bbl=111)
        + _cycle_record("2402")
        + _production_record(oil_production_bbl=222)
        + _root_record(district_code="02", lease_nbr="000002")
        + _cycle_record("2401")
        + _production_record(oil_production_bbl=333)
    )
    path = tmp_path / "PDF100.ebc"
    path.write_bytes(records)

    result = load_pdf100(path, progress_every=None)

    assert len(result["root"]) == 2
    assert list(result["cycle"]["district_code"]) == ["01", "01", "02"]
    assert list(result["cycle"]["lease_nbr"]) == ["000001", "000001", "000002"]

    prod = result["production"]
    assert list(prod["district_code"]) == ["01", "01", "02"]
    assert list(prod["rpt_cycle_key_yymm"]) == ["2401", "2402", "2401"]
    assert list(prod["oil_production_bbl"]) == [111, 222, 333]
