from pathlib import Path

import duckdb
import pandas as pd

from oil_pipeline.load.duckdb import save_tables


def test_save_tables_writes_each_dataframe_as_a_table(tmp_path: Path):
    db_path = tmp_path / "nested" / "test.duckdb"
    tables = {
        "wells": pd.DataFrame({"api_number": ["1", "2"]}),
        "oil_production": pd.DataFrame({"oil_production_bbl": [10, 20]}),
    }

    save_tables(tables, db_path)

    assert db_path.exists()
    with duckdb.connect(str(db_path), read_only=True) as con:
        assert con.execute("SELECT api_number FROM wells ORDER BY api_number").fetchall() == [
            ("1",),
            ("2",),
        ]
        assert con.execute("SELECT COUNT(*) FROM oil_production").fetchone()[0] == 2


def test_save_tables_replaces_existing_table(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"

    save_tables({"wells": pd.DataFrame({"api_number": ["1", "2", "3"]})}, db_path)
    save_tables({"wells": pd.DataFrame({"api_number": ["9"]})}, db_path)

    with duckdb.connect(str(db_path), read_only=True) as con:
        assert con.execute("SELECT api_number FROM wells").fetchall() == [("9",)]
