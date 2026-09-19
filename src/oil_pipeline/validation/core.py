"""Shared pandera validation helpers.

Every schema in this package mixes two check tiers, both expressed as
ordinary pandera Checks:

  - hard checks (the default, raise_warning=False): a violation
    contributes to a SchemaErrors failure. `validate()` re-raises this as
    ValidationError, halting the pipeline. Used for structural guarantees
    that downstream code depends on -- required columns, key uniqueness,
    known enumerations.
  - soft checks (`Check(..., raise_warning=True)`): a violation is caught
    as a SchemaWarning and logged, but does not stop the run. Used for
    known data-quality quirks documented in docs/data_*.md "Known Issues"
    that are informational rather than pipeline-breaking.
"""

import logging
import warnings

import pandas as pd
import pandera.pandas as pa

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """A hard validation check failed; the pipeline should stop."""


def validate(df: pd.DataFrame, schema: pa.DataFrameSchema, label: str) -> pd.DataFrame:
    """Validate `df` against `schema`, tagging log/error messages with `label`.

    Soft-check failures are logged as warnings and the validated DataFrame
    is returned as usual. Hard-check failures raise ValidationError with
    the failing cases attached.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", pa.errors.SchemaWarning)
        try:
            validated = schema.validate(df, lazy=True)
        except pa.errors.SchemaErrors as exc:
            cases = exc.failure_cases.to_string(index=False)
            raise ValidationError(
                f"{label}: {len(exc.failure_cases)} hard validation check(s) failed\n{cases}"
            ) from exc

    for w in caught:
        logger.warning("%s: %s", label, w.message)

    logger.info("%s: %s rows passed validation", label, f"{len(validated):,}")
    # Piggybacked via .attrs rather than changing the return type -- callers
    # that just want the DataFrame (most of them) are unaffected; assets.py
    # reads this to report validation_warnings in each asset's metadata.
    validated.attrs["validation_warnings"] = len(caught)
    return validated


def not_blank(raise_warning: bool = False) -> pa.Check:
    """A fixed-width EBCDIC text field is not empty/all-spaces after stripping."""
    return pa.Check(
        lambda s: s.str.strip().ne(""),
        element_wise=False,
        error="not_blank",
        raise_warning=raise_warning,
    )
