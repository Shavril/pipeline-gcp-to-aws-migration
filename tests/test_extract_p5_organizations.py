from pathlib import Path

from ebcdic_builders import pad, text_field

from oil_pipeline.extract.p5_organizations import RECORD_LENGTH, load_orf850, parse_organization


def _organization_record(operator_number="111111", organization_name="Acme Oil", p5_status="A") -> bytes:
    record = bytearray(text_field(" ", RECORD_LENGTH))
    pad(record, 0, text_field("A ", 2))
    pad(record, 2, text_field(operator_number, 6))
    pad(record, 8, text_field(organization_name, 32))
    pad(record, 41, text_field(p5_status, 1))
    return bytes(record)


def test_parse_organization_strips_padded_name():
    row = parse_organization(_organization_record(organization_name="Acme Oil"))
    assert row == {
        "operator_number": "111111",
        "organization_name": "Acme Oil",
        "p5_status": "A",
    }


def test_load_orf850_only_parses_organization_records(tmp_path: Path):
    other = bytearray(text_field(" ", RECORD_LENGTH))
    pad(other, 0, text_field("K ", 2))

    records = (
        _organization_record(operator_number="111111")
        + bytes(other)
        + _organization_record(operator_number="222222", p5_status="X")
    )
    path = tmp_path / "orf850.ebc"
    path.write_bytes(records)

    result = load_orf850(path, progress_every=None)

    assert len(result["organizations"]) == 2
    assert list(result["organizations"]["operator_number"]) == ["111111", "222222"]
    assert result["key_counts"].set_index("key").loc["K ", "count"] == 1
