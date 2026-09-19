"""Extract Root-segment records from the P-4 Operator/Lease Database (p4f606.ebc).

Only the Root segment (key '01') is parsed — it carries the lease key
(district_code, lease_nbr) and the current operator number, which is all
that's needed to bridge production leases to P-5 organization records.
Segment layout is documented in docs/data_p4_operators.md, derived from
data/raw/operators/p4-user-manual_p4a002_feb2015.pdf.
"""

import logging
from collections import Counter
from pathlib import Path

import pandas as pd

from oil_pipeline.utils import decode_text, iter_records

logger = logging.getLogger(__name__)

RECORD_LENGTH = 92  # bytes; p4f606.ebc fixed physical record length (p4a002.pdf)

ROOT_KEY = "01"

# All 30 segment types in the "Complete P-4" tape (docs/data_p4_operators.md).
# Only Root (01) is parsed; the rest are tallied by key for exploration only.
SEGMENT_NAMES = {
    "01": "P4ROOT (Root Segment)",
    "02": "P4INFO (General P-4 Filing Information)",
    "03": "P4GPN (Gatherer/Purchaser/Nominator)",
    "04": "P4REMARK (P-4 Remarks)",
    "05": "P4LSEPTR (Lease Pointer)",
    "06": "P4RESTR (Lease Restrictions)",
    "07": "P4LSENM (Lease Name)",
    "08": "P4LSERMK (Lease Remarks)",
    "09": "P4SEVR (Severance Information)",
    "10": "P4SEVRMK (Severance Remarks)",
    "11": "P4GSCHED (Gas Schedule Information)",
    "12": "P4GSCHCY (Gas Schedule Cycle)",
    "13": "P4GSECT (Gas Problem/Letter Section)",
    "14": "P4GLTRDT (Gas Problem/Letter Date & Type)",
    "15": "P4OSCHED (Oil Schedule Information)",
    "16": "P4OSCHCY (Oil Schedule Cycle)",
    "17": "P4OSECT (Oil Problem/Letter Section)",
    "18": "P4OLTRDT (Oil Problem/Letter Date & Type)",
    "19": "P4YATES (Yates Field Unit Information)",
    "20": "P4OUNIT (Schedule Unit Information)",
    "21": "P4OUNTCY (Schedule Unit Reporting Cycle)",
    "22": "P4OUNTPV (Previous Unit Allowable)",
    "23": "P4OUNTRK (Unit Remarks)",
    "24": "P4LSEXCP (Lease Exceptions)",
    "25": "P4CMPTR (Commingle Permit Pointer)",
    "26": "P4EXDATE (Form P-17 Exception Date)",
    "27": "P4FEEREC (P4 Fee Received)",
    "28": "P4CHECK (P4 Check Register)",
    "29": "P4SVRFEE (P4 Severance Fee)",
    "30": "P4FEEPAY (P4 Severance Fee Payment)",
}


def parse_root(record: bytes) -> dict:
    """01 — P4ROOT: one per oil lease / gas well."""
    return {
        "oil_gas_code": decode_text(record[2:3]),
        "district_code": decode_text(record[3:5]),
        "lease_nbr": decode_text(record[5:11]),
        "operator_number": decode_text(record[20:26]),
    }


def load_p4f606(path: Path, progress_every: int | None = 5_000_000) -> dict[str, pd.DataFrame]:
    """Stream p4f606.ebc once, tallying every record type and parsing Root segments.

    Set progress_every to None to disable progress logging.

    Returns a dict with:
      - "key_counts": DataFrame of record-type key, count, segment name, pct
      - "root": the parsed Root segment DataFrame, covering both oil leases
        and gas wells (oil_gas_code 'O'/'G') — filter to 'O' downstream to
        match the oil-only production tape.
    """
    key_tally: Counter[str] = Counter()
    rows = []

    n = 0
    for record in iter_records(path, RECORD_LENGTH):
        n += 1
        key = decode_text(record[0:2])
        key_tally[key] += 1
        if key == ROOT_KEY:
            rows.append(parse_root(record))
        if progress_every and n % progress_every == 0:
            logger.info("...%s records scanned", f"{n:,}")

    logger.info("Done: %s records scanned, %s Root records found", f"{n:,}", f"{len(rows):,}")

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
        "root": pd.DataFrame(rows),
    }
