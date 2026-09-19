from pathlib import Path

from ebcdic_builders import comp3_field as pack_comp3
from ebcdic_builders import zoned_field as pack_zoned_decimal

from oil_pipeline.utils import decode_text, iter_records, unpack_comp3, unpack_zoned_decimal

# ---------------------------------------------------------------------------
# decode_text
# ---------------------------------------------------------------------------


def test_decode_text_round_trips_digits_and_letters():
    text = "AB01-9"
    assert decode_text(text.encode("cp037")) == text


def test_decode_text_round_trips_spaces():
    assert decode_text("      ".encode("cp037")) == "      "


# ---------------------------------------------------------------------------
# unpack_comp3
# ---------------------------------------------------------------------------


def test_unpack_comp3_positive():
    assert unpack_comp3(pack_comp3(12345, 9)) == 12345


def test_unpack_comp3_negative():
    assert unpack_comp3(pack_comp3(-42, 9)) == -42


def test_unpack_comp3_zero():
    assert unpack_comp3(pack_comp3(0, 9)) == 0


def test_unpack_comp3_alternate_negative_sign_nibble():
    # 0xB is also a valid negative sign nibble alongside 0xD (docs/utils.py).
    field = bytearray(pack_comp3(42, 9))
    field[-1] = (field[-1] & 0xF0) | 0xB
    assert unpack_comp3(bytes(field)) == -42


# ---------------------------------------------------------------------------
# unpack_zoned_decimal
# ---------------------------------------------------------------------------


def test_unpack_zoned_decimal_positive_no_decimals():
    assert unpack_zoned_decimal(pack_zoned_decimal(31, 3)) == 31


def test_unpack_zoned_decimal_negative():
    assert unpack_zoned_decimal(pack_zoned_decimal(-31, 3)) == -31


def test_unpack_zoned_decimal_with_decimal_places():
    # Mirrors the wellbore file's latitude/longitude encoding (7 decimal places).
    packed = pack_zoned_decimal(31.1234567, 10, decimal_places=7)
    assert unpack_zoned_decimal(packed, decimal_places=7) == 31.1234567


def test_unpack_zoned_decimal_zero_sign_nibble_is_positive():
    # docs/data_wells.md: 0xF sign nibble is a "zero placeholder", treated as positive.
    field = bytearray(pack_zoned_decimal(0, 3))
    field[-1] = (0xF << 4) | (field[-1] & 0x0F)
    assert unpack_zoned_decimal(bytes(field)) == 0


# ---------------------------------------------------------------------------
# iter_records
# ---------------------------------------------------------------------------


def test_iter_records_splits_fixed_length_records(tmp_path: Path):
    record_length = 10
    records = [bytes([i]) * record_length for i in range(5)]
    path = tmp_path / "sample.ebc"
    path.write_bytes(b"".join(records))

    result = list(iter_records(path, record_length))

    assert result == records


def test_iter_records_across_chunk_boundaries(tmp_path: Path):
    # chunk_records smaller than the total record count forces multiple reads.
    record_length = 4
    records = [bytes([i]) * record_length for i in range(10)]
    path = tmp_path / "sample.ebc"
    path.write_bytes(b"".join(records))

    result = list(iter_records(path, record_length, chunk_records=3))

    assert result == records


def test_iter_records_empty_file(tmp_path: Path):
    path = tmp_path / "empty.ebc"
    path.write_bytes(b"")

    assert list(iter_records(path, 10)) == []
