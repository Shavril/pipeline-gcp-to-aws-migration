"""Structural validation for extract-layer output (right after EBCDIC decode).

Hard checks confirm the parse produced structurally sound data: required
columns present and non-blank, fixed field widths honored, and the grain
each downstream transform relies on. Soft checks surface known messy
fields called out in docs/data_*.md "Known Issues" without stopping the
run -- these are informational, not pipeline-breaking.

Called from each raw asset (dagster_defs/assets.py) immediately after its
load_* extract function, before anything is written to DuckDB.
"""

import pandas as pd
from pandera.pandas import Check, Column, DataFrameSchema

from oil_pipeline.validation.core import not_blank, validate

# coerce=True throughout this module: text columns arrive as plain
# `object`-dtype Python strings regardless of source (dict-built DataFrames
# from the extract layer, or DuckDB's fetchdf()), but pandera's `str` dtype
# check expects the pandas "string[pyarrow]" extension dtype specifically.
# coerce=True casts rather than hard-failing on that storage difference,
# which isn't a real data-quality signal.
_DISTRICT_CODE = Column(str, [not_blank(), Check.str_length(2, 2)], coerce=True)
_LEASE_NBR_6 = Column(str, [not_blank(), Check.str_length(6, 6)], coerce=True)
_CYCLE_KEY = Column(str, [not_blank(), Check.str_matches(r"^\d{4}$")], coerce=True)

# ---------------------------------------------------------------------------
# Production (PDF100.ebc)
# ---------------------------------------------------------------------------

_PRODUCTION_ROOT_SCHEMA = DataFrameSchema(
    {
        "oil_code": Column(str, Check.isin(["O"], raise_warning=True), coerce=True),
        "district_code": _DISTRICT_CODE,
        "lease_nbr": _LEASE_NBR_6,
        "movable_balance_bbl": Column(int),
        "beginning_oil_status_bbl": Column(int),
        "beginning_csghd_status_mcf": Column(int),
        "oldest_eom_balance_bbl": Column(int),
    },
    unique=["district_code", "lease_nbr"],
)

_PRODUCTION_CYCLE_SCHEMA = DataFrameSchema(
    {
        "district_code": _DISTRICT_CODE,
        "lease_nbr": _LEASE_NBR_6,
        "rpt_cycle_key_yymm": _CYCLE_KEY,
    },
    unique=["district_code", "lease_nbr", "rpt_cycle_key_yymm"],
)

_PRODUCTION_PRODUCTION_SCHEMA = DataFrameSchema(
    {
        "district_code": _DISTRICT_CODE,
        "lease_nbr": _LEASE_NBR_6,
        "rpt_cycle_key_yymm": _CYCLE_KEY,
        # build_oil_production inner-joins production+cycle on this triple
        # and the docstring there asserts it's verified 1:1 -- a duplicate
        # here would silently fan out that join.
        "oil_production_bbl": Column(int, Check.ge(0, raise_warning=True)),
        "casinghead_gas_mcf": Column(int, Check.ge(0, raise_warning=True)),
    },
    unique=["district_code", "lease_nbr", "rpt_cycle_key_yymm"],
)


def validate_production_raw(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate the root/cycle/production tables returned by load_pdf100."""
    return {
        **tables,
        "root": validate(tables["root"], _PRODUCTION_ROOT_SCHEMA, "production.root"),
        "cycle": validate(tables["cycle"], _PRODUCTION_CYCLE_SCHEMA, "production.cycle"),
        "production": validate(tables["production"], _PRODUCTION_PRODUCTION_SCHEMA, "production.production"),
    }


# ---------------------------------------------------------------------------
# P-4 Operators (p4f606.ebc)
# ---------------------------------------------------------------------------

_P4_ROOT_SCHEMA = DataFrameSchema(
    {
        "oil_gas_code": Column(str, Check.isin(["O", "G"]), coerce=True),
        "district_code": _DISTRICT_CODE,
        "lease_nbr": _LEASE_NBR_6,
        # Blank operator_number breaks the downstream P-5 join, but the
        # file's full extent isn't independently confirmed to always
        # populate it -- soft, not hard.
        "operator_number": Column(str, not_blank(raise_warning=True), coerce=True),
    },
    checks=[
        # oil_gas_code is part of the intended grain: docs/data_p4_operators.md
        # notes the file mixes oil+gas records, and a gas well can
        # coincidentally share a (district_code, lease_nbr) with an oil
        # lease. But confirmed against real data: the tape itself contains
        # exact duplicate root records for the same lease (byte-identical,
        # same operator_number) -- a genuine source-data quirk, not decode
        # corruption, so soft rather than hard. build_lease_operators
        # dedupes defensively downstream to guarantee its one-row-per-lease
        # grain regardless.
        Check(
            lambda df: ~df.duplicated(subset=["oil_gas_code", "district_code", "lease_nbr"]),
            raise_warning=True,
            error="(oil_gas_code, district_code, lease_nbr) repeats",
        )
    ],
)


def validate_p4_raw(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate the root table returned by load_p4f606."""
    return {**tables, "root": validate(tables["root"], _P4_ROOT_SCHEMA, "p4.root")}


# ---------------------------------------------------------------------------
# P-5 Organizations (orf850.ebc)
# ---------------------------------------------------------------------------

_P5_ORGANIZATIONS_SCHEMA = DataFrameSchema(
    {
        "operator_number": Column(str, not_blank(), coerce=True),
        "organization_name": Column(str, not_blank(), coerce=True),
        # Structurally a single non-blank character (hard). Which characters
        # are valid is a separate, softer question: A, I, D, S are
        # documented; X, H, R are real but undocumented
        # (docs/data_p5_organizations.md Known Issues) -- soft so genuinely
        # new codes are surfaced rather than silently dropped or hard-failed.
        "p5_status": Column(
            str,
            [
                Check.str_length(1, 1),
                Check.isin(["A", "I", "D", "S", "X", "H", "R"], raise_warning=True),
            ],
            coerce=True,
        ),
    },
    checks=[
        # Whether an operator can have more than one 'A ' record over time
        # is an open question (docs/data_p5_organizations.md) -- soft.
        Check(
            lambda df: ~df["operator_number"].duplicated(),
            raise_warning=True,
            error="operator_number repeats across organization records",
        )
    ],
)


def validate_p5_raw(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate the organizations table returned by load_orf850."""
    return {
        **tables,
        "organizations": validate(tables["organizations"], _P5_ORGANIZATIONS_SCHEMA, "p5.organizations"),
    }


# ---------------------------------------------------------------------------
# Wells (dbf900.ebc)
# ---------------------------------------------------------------------------

_WELLS_ROOT_SCHEMA = DataFrameSchema(
    {
        "api_number": Column(str, [not_blank(), Check.str_length(8, 8)], unique=True, coerce=True),
        # Root's field_district is known to be blank on the majority of
        # records (docs/data_wells.md) -- Completion's district_code is
        # used downstream instead, so this is informational only.
        "field_district": Column(str, Check(lambda s: s.str.strip().ne(""), raise_warning=True), coerce=True),
        "orig_compl_year": Column(str, Check.str_matches(r"^\d{4}$"), coerce=True),
        # Right-justified/space-padded rather than zero-padded on a small
        # subset of real records (confirmed: 37 of 1,211,829 root records,
        # e.g. "    0") -- DuckDB's CAST(... AS INTEGER) in transform/wells.py
        # already tolerates this padding, so strip before checking digits.
        "total_depth": Column(
            str, Check(lambda s: s.str.strip().str.match(r"^\d+$"), error="numeric_after_strip"), coerce=True
        ),
    },
)

_WELLS_COMPLETION_SCHEMA = DataFrameSchema(
    {
        "api_number": Column(str, [not_blank(), Check.str_length(8, 8)], coerce=True),
        "district_code": _DISTRICT_CODE,
        "lease_nbr": Column(str, [not_blank(), Check.str_length(5, 5)], coerce=True),
        "oil_code": Column(str, Check.isin(["O", "G"], raise_warning=True), coerce=True),
    },
)

_WELLS_NEW_LOCATION_SCHEMA = DataFrameSchema(
    {
        "api_number": Column(str, [not_blank(), Check.str_length(8, 8)], coerce=True),
        # Texas's actual bounding box (docs/data_wells.md); (0, 0) placeholder
        # rows are nulled out downstream in transform/wells.py, not here.
        "latitude": Column(float, Check.in_range(25.86, 36.50, raise_warning=True), nullable=True),
        "longitude": Column(float, Check.in_range(-106.54, -93.53, raise_warning=True), nullable=True),
    },
)


def validate_wells_raw(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate the root/completion/new_location tables returned by load_dbf900."""
    return {
        **tables,
        "root": validate(tables["root"], _WELLS_ROOT_SCHEMA, "wells.root"),
        "completion": validate(tables["completion"], _WELLS_COMPLETION_SCHEMA, "wells.completion"),
        "new_location": validate(tables["new_location"], _WELLS_NEW_LOCATION_SCHEMA, "wells.new_location"),
    }
