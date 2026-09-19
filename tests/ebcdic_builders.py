"""Shared helpers for building synthetic EBCDIC fixed-width test records.

Each function is the inverse of one of oil_pipeline.utils's decode helpers,
used to hand-construct byte fields for extract-layer parser tests.
"""


def text_field(value: str, width: int) -> bytes:
    """A left-justified, space-padded EBCDIC text field of exactly `width` bytes."""
    return value.ljust(width)[:width].encode("cp037")


def comp3_field(value: int, n_digits: int) -> bytes:
    """An IBM COMP-3 (packed decimal) field encoding `value` over `n_digits` digits."""
    sign_nibble = 0xD if value < 0 else 0xC
    digits = [int(d) for d in str(abs(value)).zfill(n_digits)]
    nibbles = digits + [sign_nibble]
    if len(nibbles) % 2:
        nibbles = [0] + nibbles
    return bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))


def zoned_field(value: float, n_digits: int, decimal_places: int = 0) -> bytes:
    """A signed zoned-decimal (DISPLAY, trailing overpunch sign) field."""
    scaled = round(abs(value) * (10**decimal_places))
    digits = [int(d) for d in str(scaled).zfill(n_digits)]
    sign_nibble = 0xD if value < 0 else 0xC
    field = bytearray(0xF0 | d for d in digits)
    field[-1] = (sign_nibble << 4) | digits[-1]
    return bytes(field)


def pad(record: bytearray, offset: int, field: bytes) -> None:
    """Write `field` into `record` at `offset`, in place."""
    record[offset : offset + len(field)] = field
