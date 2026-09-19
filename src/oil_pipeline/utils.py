"""Low-level EBCDIC / packed-decimal decoding and fixed-length record streaming
helpers, shared across all four RRC tape formats used in this project
(production, P-4 operators, P-5 organizations, wellbore)."""

from pathlib import Path

# Assumed IBM EBCDIC code page 037 (US/Canada) -- validated against decoded
# data from all three RRC tape files.
ENCODING = "cp037"

_NEGATIVE_SIGN_NIBBLES = {0xD, 0xB}


def decode_text(field: bytes, encoding: str = ENCODING) -> str:
    """Decode an EBCDIC text/digit field to a Python str."""
    return field.decode(encoding)


def unpack_comp3(field: bytes) -> int:
    """Unpack an IBM COMP-3 (packed decimal) field into a signed int.

    Each byte holds two BCD digits, except the last byte, whose low nibble
    is the sign (C/F = positive, D/B = negative) rather than a digit.
    """
    digits = []
    for byte in field[:-1]:
        digits.append((byte >> 4) & 0xF)
        digits.append(byte & 0xF)
    digits.append((field[-1] >> 4) & 0xF)
    sign_nibble = field[-1] & 0xF

    value = int("".join(str(d) for d in digits))
    return -value if sign_nibble in _NEGATIVE_SIGN_NIBBLES else value


def unpack_zoned_decimal(field: bytes, decimal_places: int = 0) -> float:
    """Unpack a signed zoned-decimal (COBOL PIC S9(n)V9(m) DISPLAY) field.

    Unlike COMP-3 (packed, two digits per byte), zoned-decimal DISPLAY
    fields store one digit per byte in the low nibble; the high nibble is
    normally an unsigned zone (0xF) except on the *last* byte, where it
    carries the sign via trailing overpunch (0xC/0xF = positive,
    0xD = negative). Used for the wellbore file's lat/long fields.
    """
    digits = [byte & 0xF for byte in field]
    sign_nibble = (field[-1] >> 4) & 0xF

    value = int("".join(str(d) for d in digits))
    if decimal_places:
        value = value / (10**decimal_places)
    return -value if sign_nibble == 0xD else value


def iter_records(path: Path, record_length: int, chunk_records: int = 500_000):
    """Stream fixed-length records from disk, one chunk_records-sized read at a time.

    record_length is required (not defaulted) since each RRC tape format has
    its own physical record length — production is 102 bytes, P-4 is 92,
    P-5 is 350.
    """
    chunk_bytes = chunk_records * record_length
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_bytes)
            if not chunk:
                return
            for i in range(0, len(chunk), record_length):
                yield chunk[i : i + record_length]
