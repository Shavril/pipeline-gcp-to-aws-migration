"""Persist DataFrames into a local DuckDB database file.

Physical database files live under data/database/ (excluded from git, see
.gitignore), consistent with CLAUDE.md's "Development: Parquet files,
DuckDB" storage guidance.
"""

import logging
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


def save_tables(tables: dict[str, pd.DataFrame], db_path: Path) -> None:
    """Write each DataFrame in `tables` as a table in a DuckDB database file.

    Each table is replaced wholesale (CREATE OR REPLACE) — this is a full
    reload, not an incremental upsert.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as con:
        for name, df in tables.items():
            con.register("_incoming", df)
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _incoming')
            con.unregister("_incoming")
            logger.info("Wrote table %r (%s rows) to %s", name, f"{len(df):,}", db_path)
