"""Extract Root, Completion, and New Location records from the Well Bore
Database (dbf900.ebc).

Segment layout is documented in docs/data_wells.md, derived from
data/raw/wells/wba091_well-bore-database.pdf. Unlike the production and
P-4 tapes (deeply nested hierarchies), this tape is a flat fan-out: every
segment type (02-28) is a direct child of the most recent Root (01)
record. Root carries the well's API number but no district/lease key;
Completion (02) carries its own (district, lease_nbr, well_nbr) directly —
matching the production/P-4 lease key — but New Location (13) only
carries county + lat/long, tied to a specific well only by its position
in the file. This module stamps api_number (from Root) onto every child
record so Completion and New Location can be joined back together later.
"""

import logging
from collections import Counter
from pathlib import Path

import pandas as pd

from oil_pipeline.utils import decode_text, iter_records, unpack_zoned_decimal

logger = logging.getLogger(__name__)

RECORD_LENGTH = 247  # bytes; dbf900.ebc fixed physical record length (wba091.pdf)

ROOT_KEY = "01"

# All 28 segment types (docs/data_wells.md). Only Root (01), Completion
# (02), and New Location (13) are parsed; the rest are tallied by key only.
SEGMENT_NAMES = {
    "01": "WBROOT (Well Bore Technical Data Root)",
    "02": "WBCOMPL (Well Bore Completion Information)",
    "03": "WBDATE (Well Bore Technical Data Forms File Date)",
    "04": "WBRMKS (Well Bore Remarks)",
    "05": "WBTUBE (Well Bore Tubing)",
    "06": "WBCASE (Well Bore Casing)",
    "07": "WBPERF (Well Bore Perforations)",
    "08": "WBLINE (Well Bore Liner)",
    "09": "WBFORM (Well Bore Formation)",
    "10": "WBSQEZE (Well Bore Squeeze)",
    "11": "WBFRESH (Well Bore Usable Quality Water Protection)",
    "12": "WBOLDLOC (Well Bore Old Location)",
    "13": "WBNEWLOC (Well Bore New Location)",
    "14": "WBPLUG (Well Bore Plugging Data)",
    "15": "WBPLRMKS (Well Bore Plugging Remarks)",
    "16": "WBPLREC (Well Bore Plugging Record)",
    "17": "WBPLCASE (Well Bore Plugging Data Casing-Tubing)",
    "18": "WBPLPERF (Well Bore Plugging Perfs)",
    "19": "WBPLNAME (Well Bore Plugging Data Nomenclature)",
    "20": "WBDRILL (Well Bore Drilling Permit Number)",
    "21": "WBWELLID (Well Bore Well-ID)",
    "22": "WB14B2 (14B2 Well)",
    "23": "WBH15 (H-15 Report)",
    "24": "WBH15RMK (H-15 Remarks)",
    "25": "WBSB126 (Senate Bill 126, 2-Yr Inactive Program)",
    "26": "WBDASTAT (Well Bore Drilling Permit Status)",
    "27": "WBW3C (Well Bore W3C Data)",
    "28": "WB14B2RM (Well Bore 14B2 Remarks)",
}


def parse_root(record: bytes) -> dict:
    """01 — WBROOT: one per well bore (API number)."""
    return {
        "api_number": decode_text(record[2:5]) + decode_text(record[5:10]),
        "field_district": decode_text(record[14:16]),
        "res_cnty_code": decode_text(record[16:19]),
        "orig_compl_year": decode_text(record[20:24]),
        "orig_compl_month": decode_text(record[24:26]),
        "orig_compl_day": decode_text(record[26:28]),
        "total_depth": decode_text(record[28:33]),
        "plug_flag": decode_text(record[90:91]),
        "water_land_code": decode_text(record[131:132]),
    }


def parse_completion(record: bytes) -> dict:
    """02 — WBCOMPL: reported oil-lease completion for a well (recurring)."""
    return {
        "oil_code": decode_text(record[2:3]),
        "district_code": decode_text(record[3:5]),
        "lease_nbr": decode_text(record[5:10]),
        "well_nbr": decode_text(record[10:16]),
        "active_inactive_code": decode_text(record[45:46]),
    }


def parse_new_location(record: bytes) -> dict:
    """13 — WBNEWLOC: modern GPS surface location for a well (non-recurring).

    WB-WGS84-LONGITUDE is stored as an unsigned magnitude (sign nibble is
    always 0xC/positive or 0xF/zero-placeholder across a ~50,000-record
    sample spanning the full file) with an implicit West convention, since
    all Texas wells sit west of the prime meridian. Negated here so the
    value is standard signed longitude, usable directly by mapping tools.
    """
    return {
        "loc_county": decode_text(record[2:5]),
        "latitude": unpack_zoned_decimal(record[132:142], decimal_places=7),
        "longitude": -unpack_zoned_decimal(record[142:152], decimal_places=7),
    }


PARSERS = {
    "01": parse_root,
    "02": parse_completion,
    "13": parse_new_location,
}


def load_dbf900(path: Path, progress_every: int | None = 5_000_000) -> dict[str, pd.DataFrame]:
    """Stream dbf900.ebc once, tallying every record type and parsing Root,
    Completion, and New Location segments.

    Every record between one Root (01) record and the next belongs to that
    well — api_number is stamped from Root onto every Completion/New
    Location record encountered in between, so the two (self-sufficient
    lease key on Completion, lat/long on New Location) can be joined back
    together downstream.

    Set progress_every to None to disable progress logging.

    Returns a dict with:
      - "key_counts": DataFrame of record-type key, count, segment name, pct
      - "root", "completion", "new_location": parsed segment DataFrames
    """
    key_tally: Counter[str] = Counter()
    parsed: dict[str, list[dict]] = {key: [] for key in PARSERS}

    current_api = None

    n = 0
    for record in iter_records(path, RECORD_LENGTH):
        n += 1
        key = decode_text(record[0:2])
        key_tally[key] += 1
        parser = PARSERS.get(key)
        if parser is not None:
            row = parser(record)
            if key == ROOT_KEY:
                current_api = row["api_number"]
            else:
                row["api_number"] = current_api
            parsed[key].append(row)
        if progress_every and n % progress_every == 0:
            logger.info("...%s records scanned", f"{n:,}")

    logger.info("Done: %s records scanned", f"{n:,}")

    key_counts = (
        pd.Series(key_tally)
        .rename_axis("key")
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )
    key_counts["segment"] = key_counts["key"].map(SEGMENT_NAMES).fillna("UNKNOWN KEY")
    key_counts["pct"] = (key_counts["count"] / key_counts["count"].sum() * 100).round(2)

    return {
        "key_counts": key_counts,
        "root": pd.DataFrame(parsed["01"]),
        "completion": pd.DataFrame(parsed["02"]),
        "new_location": pd.DataFrame(parsed["13"]),
    }
