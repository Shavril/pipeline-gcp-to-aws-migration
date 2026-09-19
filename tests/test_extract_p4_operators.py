from pathlib import Path

from ebcdic_builders import pad, text_field

from oil_pipeline.extract.p4_operators import RECORD_LENGTH, load_p4f606, parse_root


def _root_record(oil_gas_code="O", district_code="01", lease_nbr="000001", operator_number="123456") -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("01", 2))
    pad(record, 2, text_field(oil_gas_code, 1))
    pad(record, 3, text_field(district_code, 2))
    pad(record, 5, text_field(lease_nbr, 6))
    pad(record, 20, text_field(operator_number, 6))
    return bytes(record)


def _other_record(key: str) -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field(key, 2))
    return bytes(record)


def test_parse_root():
    row = parse_root(_root_record())
    assert row == {
        "oil_gas_code": "O",
        "district_code": "01",
        "lease_nbr": "000001",
        "operator_number": "123456",
    }


def test_load_p4f606_only_parses_root_segments(tmp_path: Path):
    records = (
        _root_record(oil_gas_code="O", lease_nbr="000001")
        + _other_record("05")
        + _other_record("07")
        + _root_record(oil_gas_code="G", lease_nbr="000002")
    )
    path = tmp_path / "p4f606.ebc"
    path.write_bytes(records)

    result = load_p4f606(path, progress_every=None)

    assert len(result["root"]) == 2
    assert list(result["root"]["oil_gas_code"]) == ["O", "G"]
    assert result["key_counts"].set_index("key").loc["05", "count"] == 1
    assert result["key_counts"].set_index("key").loc["07", "count"] == 1
