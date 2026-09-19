"""Extract Organization ('A ') records from the P-5 Organization Report Database (orf850.ebc).

Only the 'A ' record is parsed — it carries the operator/organization
number and company name, which is all that's needed to resolve an
operator number into a company name. Segment layout is documented in
docs/data_p5_organizations.md, derived from
data/raw/organizations/ora001_p5_manual_october-2014.pdf.
"""

import logging
from collections import Counter
from pathlib import Path

import pandas as pd

from oil_pipeline.utils import decode_text, iter_records

logger = logging.getLogger(__name__)

RECORD_LENGTH = 350  # bytes; orf850.ebc fixed physical record length (ora001.pdf)

ORGANIZATION_KEY = "A "

# All 9 record types on the P-5 tape (docs/data_p5_organizations.md). Only
# 'A ' is parsed; the rest are tallied by key for exploration only.
SEGMENT_NAMES = {
    "1T": "Specialty/Activity Code Table (not org-specific)",
    "A ": "Organization Information (Root)",
    "F ": "Specialty Codes (specialty mailing addresses)",
    "H ": "Specialty Addresses by District",
    "J ": "Field Information (reserved for future use)",
    "K ": "Officer/Agent Information",
    "P ": "Remarks (RRC internal use)",
    "U ": "Activity Indicators",
    "R ": "Activity Restrictions",
}


def parse_organization(record: bytes) -> dict:
    """'A ' — Organization Information: one per organization (company)."""
    return {
        "operator_number": decode_text(record[2:8]),
        "organization_name": decode_text(record[8:40]).strip(),
        "p5_status": decode_text(record[41:42]),
    }


def load_orf850(path: Path, progress_every: int | None = 2_000_000) -> dict[str, pd.DataFrame]:
    """Stream orf850.ebc once, tallying every record type and parsing 'A ' (Organization) records.

    Set progress_every to None to disable progress logging.

    Returns a dict with:
      - "key_counts": DataFrame of record-type key, count, segment name, pct
      - "organizations": the parsed Organization DataFrame
    """
    key_tally: Counter[str] = Counter()
    rows = []

    n = 0
    for record in iter_records(path, RECORD_LENGTH):
        n += 1
        key = decode_text(record[0:2])
        key_tally[key] += 1
        if key == ORGANIZATION_KEY:
            rows.append(parse_organization(record))
        if progress_every and n % progress_every == 0:
            logger.info("...%s records scanned", f"{n:,}")

    logger.info("Done: %s records scanned, %s Organization records found", f"{n:,}", f"{len(rows):,}")

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
        "organizations": pd.DataFrame(rows),
    }
