"""Persist DataFrames into local Parquet files.

Physical Parquet files live under data/processed/ (excluded from git, see
.gitignore) — regenerable from the DuckDB tables.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def save_parquet(tables: dict[str, pd.DataFrame], processed_dir: Path) -> dict[str, Path]:
    """Write each DataFrame in `tables` to its own Parquet file under processed_dir.

    Returns a dict mapping table name to the Parquet file path written.
    """
    processed_dir.mkdir(parents=True, exist_ok=True)

    paths = {}
    for name, df in tables.items():
        path = processed_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        paths[name] = path
        logger.info("Wrote %s rows to %s", f"{len(df):,}", path)

    return paths
