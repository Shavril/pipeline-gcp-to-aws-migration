"""Extract raw records from the RRC Statewide Production Data (Oil) tape file (PDF100.ebc).

Segment layouts and field positions are documented in docs/data_rrc_production.md,
derived from data/raw/production/pda001.pdf.
"""

import logging
from collections import Counter
from pathlib import Path

import pandas as pd

from oil_pipeline.utils import decode_text, iter_records, unpack_comp3

logger = logging.getLogger(__name__)

RECORD_LENGTH = 102  # bytes; PDF100.ebc fixed physical record length (pda001.pdf)

SEGMENT_NAMES = {
    "01": "PDROOT (Root Segment)",
    "02": "PDORPTCY (Reporting Cycle Segment)",
    "03": "PDOPROD (Production Segment)",
    "04": "PDORMVDS (Discrepancy Removal Segment)",
    "05": "PDODSP (Disposition & Stock Adjustment)",
    "06": "PDOCSHDS (Casinghead Disposition)",
    "07": "PDOPRPV (Previous Production Report)",
    "08": "PDOCMPMT (Commingle Permit)",
    "09": "PDOCMPRD (Commingle Production)",
    "10": "PDOCMODS (Commingle Oil Disposition)",
    "11": "PDOOEB (Commingle Oldest Ending Balance)",
    "12": "PDOCMPV (Commingle Previous Prod Report)",
    "13": "PDOPRVAL (Previous Allowable)",
    "22": "PDREMARK (Production Remarks)",
    "23": "PDODSPRK (Oil Disposition Remarks)",
    "24": "PDOCMGRK (Oil Commingle Disposition Remarks)",
}


def parse_root(record: bytes) -> dict:
    """01 — PDROOT: one per oil lease."""
    return {
        "oil_code": decode_text(record[2:3]),
        "district_code": decode_text(record[3:5]),
        "lease_nbr": decode_text(record[5:11]),
        "movable_balance_bbl": unpack_comp3(record[11:16]),
        "beginning_oil_status_bbl": unpack_comp3(record[16:21]),
        "beginning_csghd_status_mcf": unpack_comp3(record[21:26]),
        "oldest_eom_balance_bbl": unpack_comp3(record[26:31]),
    }


def parse_reporting_cycle(record: bytes) -> dict:
    """02 — PDORPTCY: one per lease per reporting cycle (month)."""
    return {
        "rpt_cycle_key_yymm": decode_text(record[2:6]),
        "daily_oil_prorated_allow": unpack_comp3(record[6:11]),
        "daily_oil_exempt_allow": unpack_comp3(record[11:16]),
        "daily_csh_prorated_allow": unpack_comp3(record[16:21]),
        "daily_csh_exempt_allow": unpack_comp3(record[21:26]),
        "oil_allowable_cycle_bbls": unpack_comp3(record[26:31]),
        "csh_limit_cycle_mcf": unpack_comp3(record[31:36]),
        "oil_ending_balance_bbl": unpack_comp3(record[52:57]),
        "present_oil_status_bbl": unpack_comp3(record[57:62]),
        "present_csghd_status_mcf": unpack_comp3(record[62:67]),
    }


def parse_production(record: bytes) -> dict:
    """03 — PDOPROD: reported oil/casinghead-gas volumes for one cycle."""
    return {
        "corrected_report_flag": decode_text(record[2:3]),
        "oil_production_bbl": unpack_comp3(record[6:11]),
        "casinghead_gas_mcf": unpack_comp3(record[11:16]),
        "casinghead_gas_lift_mcf": unpack_comp3(record[16:21]),
        "batch_number": decode_text(record[21:24]),
        "item_number": decode_text(record[24:28]),
        "posting_year": decode_text(record[28:32]),
        "posting_month": decode_text(record[32:34]),
        "posting_day": decode_text(record[34:36]),
        "filed_by_edi_flag": decode_text(record[36:37]),
    }


def parse_prev_production_report(record: bytes) -> dict:
    """07 — PDOPRPV: posting metadata for the previous production report."""
    return {
        "prev_posting_year": decode_text(record[2:6]),
        "prev_posting_month": decode_text(record[6:8]),
        "prev_posting_day": decode_text(record[8:10]),
        "prev_batch_number": decode_text(record[10:13]),
        "prev_item_number": decode_text(record[13:17]),
        "prev_changed_flag": decode_text(record[17:18]),
        "prev_filed_by_edi_flag": decode_text(record[18:19]),
    }


PARSERS = {
    "01": parse_root,
    "02": parse_reporting_cycle,
    "03": parse_production,
    "07": parse_prev_production_report,
}

ROOT_KEY = "01"
CYCLE_KEY = "02"
# Segments that hang directly off Root without going through a Reporting
# Cycle segment (PDREMARK and its children) — not currently parsed, listed
# here so they're excluded from cycle-key propagation if added later.
ROOT_ONLY_KEYS = {"22", "23", "24"}


def load_pdf100(path: Path, progress_every: int | None = 2_000_000) -> dict[str, pd.DataFrame]:
    """Stream PDF100.ebc once, tallying every record type and parsing the core segments.

    Segments carry no explicit foreign key to their parent lease/cycle — the
    relationship is positional (each segment belongs to whichever Root/
    Reporting Cycle segment most recently preceded it in the file). This
    walks the file in order, tracking the current lease and reporting cycle,
    and stamps district_code + lease_nbr (and, for cycle children,
    rpt_cycle_key_yymm) onto every parsed row so the segments can be joined
    downstream.

    Set progress_every to None to disable progress logging.

    Returns a dict with:
      - "key_counts": DataFrame of record-type key, count, segment name, pct
      - "root", "cycle", "production", "prev_production": parsed segment DataFrames
    """
    key_tally: Counter[str] = Counter()
    parsed: dict[str, list[dict]] = {key: [] for key in PARSERS}

    current_lease = None  # (district_code, lease_nbr) of the most recent Root segment
    current_cycle_key = None  # rpt_cycle_key_yymm of the most recent Reporting Cycle segment

    n = 0
    for record in iter_records(path, RECORD_LENGTH):
        n += 1
        key = decode_text(record[0:2])
        key_tally[key] += 1
        parser = PARSERS.get(key)
        if parser is not None:
            row = parser(record)

            if key == ROOT_KEY:
                current_lease = (row["district_code"], row["lease_nbr"])
                current_cycle_key = None
            else:
                row["district_code"] = current_lease[0] if current_lease else None
                row["lease_nbr"] = current_lease[1] if current_lease else None

            if key == CYCLE_KEY:
                current_cycle_key = row["rpt_cycle_key_yymm"]
            elif key not in (ROOT_KEY, *ROOT_ONLY_KEYS):
                row["rpt_cycle_key_yymm"] = current_cycle_key

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
        "cycle": pd.DataFrame(parsed["02"]),
        "production": pd.DataFrame(parsed["03"]),
        "prev_production": pd.DataFrame(parsed["07"]),
    }
