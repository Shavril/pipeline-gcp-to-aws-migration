"""Business-rule validation for the analytics tables built by transform/*.py.

Hard checks here mostly re-assert guarantees the transform SQL already
enforces (e.g. total_depth_ft's 1-40,000 range, filtered in
transform/wells.py) -- a violation means the SQL regressed, so it's worth
stopping the run over. Soft checks surface data-quality signals that
aren't (and shouldn't be) enforced upstream, per docs/data_*.md "Known
Issues".

Called from each transform asset (dagster_defs/assets.py) on its build_*
function's output, before it's saved to DuckDB/Parquet.
"""

import pandas as pd
from pandera.pandas import Check, Column, DataFrameSchema

from oil_pipeline.validation.core import validate

# coerce=True on every text column: DuckDB's fetchdf() returns plain
# `object`-dtype Python strings, but pandera's `str` dtype check expects
# the pandas "string[pyarrow]" extension dtype -- coerce=True casts rather
# than hard-failing on that storage difference, which isn't a real
# data-quality signal.

# ---------------------------------------------------------------------------
# oil_production
# ---------------------------------------------------------------------------

_OIL_PRODUCTION_SCHEMA = DataFrameSchema(
    {
        "district_code": Column(str, coerce=True),
        "lease_nbr": Column(str, coerce=True),
        "report_month": Column(checks=Check(lambda s: s.notna())),
        "oil_production_bbl": Column(int, Check.ge(0, raise_warning=True)),
        "casinghead_gas_mcf": Column(int, Check.ge(0, raise_warning=True)),
        # Static code->id lookup (transform/districts.py); a null here means
        # district_code held a value the lookup table doesn't know about.
        "rrc_district_id": Column(str, Check(lambda s: s.notna(), raise_warning=True), nullable=True, coerce=True),
    },
    # Matches build_oil_production's documented grain: one row per
    # lease per reporting month.
    unique=["district_code", "lease_nbr", "report_month"],
)


def validate_oil_production(df: pd.DataFrame) -> pd.DataFrame:
    return validate(df, _OIL_PRODUCTION_SCHEMA, "oil_production")


# ---------------------------------------------------------------------------
# lease_operators
# ---------------------------------------------------------------------------

_LEASE_OPERATORS_SCHEMA = DataFrameSchema(
    {
        "district_code": Column(str, coerce=True),
        "lease_nbr": Column(str, coerce=True),
        "lease_id": Column(str, nullable=False, coerce=True),
        "operator_number": Column(str, coerce=True),
        # LEFT JOIN to P-5 by design (see build_lease_operators docstring) --
        # nulls are expected for unmatched operators, so nullable, but a
        # join that's badly broken should still be visible.
        "organization_name": Column(str, nullable=True, coerce=True),
    },
    checks=[
        Check(
            lambda df: len(df) == 0 or df["organization_name"].isna().mean() < 0.10,
            raise_warning=True,
            error="organization_name null rate >= 10% -- possible P-5 join regression",
        )
    ],
    # Matches build_lease_operators's documented grain: one row per oil lease.
    unique=["district_code", "lease_nbr"],
)


def validate_lease_operators(df: pd.DataFrame) -> pd.DataFrame:
    return validate(df, _LEASE_OPERATORS_SCHEMA, "lease_operators")


# ---------------------------------------------------------------------------
# wells
# ---------------------------------------------------------------------------

_WELLS_SCHEMA = DataFrameSchema(
    {
        "api_number": Column(str, unique=True, coerce=True),
        "lease_id": Column(str, nullable=False, coerce=True),
        # Already filtered to this range in transform/wells.py -- re-checked
        # here as a regression guard, so hard. dtype left unchecked since
        # DuckDB's nullable INTEGER can surface as float64 or Int64.
        "total_depth_ft": Column(checks=Check.in_range(1, 40_000), nullable=True),
        "orig_compl_year": Column(checks=Check.in_range(1900, 2026), nullable=True),
        # Texas's actual bounding box (docs/data_wells.md) -- a non-null
        # value outside it would be a real anomaly, not the known (0, 0)
        # placeholder case (already nulled upstream), so soft.
        "latitude": Column(checks=Check.in_range(25.86, 36.50, raise_warning=True), nullable=True),
        "longitude": Column(checks=Check.in_range(-106.54, -93.53, raise_warning=True), nullable=True),
    },
    # Matches build_wells's documented grain: one row per well.
    unique=["api_number"],
)


def validate_wells(df: pd.DataFrame) -> pd.DataFrame:
    return validate(df, _WELLS_SCHEMA, "wells")
