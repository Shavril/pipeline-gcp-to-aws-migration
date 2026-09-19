from pathlib import Path

import pandas as pd

from oil_pipeline.load.parquet import save_parquet


def test_save_parquet_round_trips_each_table(tmp_path: Path):
    processed_dir = tmp_path / "processed"
    tables = {
        "wells": pd.DataFrame({"api_number": ["1", "2"]}),
        "oil_production": pd.DataFrame({"oil_production_bbl": [10, 20]}),
    }

    paths = save_parquet(tables, processed_dir)

    assert set(paths) == {"wells", "oil_production"}
    assert paths["wells"] == processed_dir / "wells.parquet"
    pd.testing.assert_frame_equal(pd.read_parquet(paths["wells"]), tables["wells"])
    pd.testing.assert_frame_equal(pd.read_parquet(paths["oil_production"]), tables["oil_production"])


def test_save_parquet_creates_processed_dir_if_missing(tmp_path: Path):
    processed_dir = tmp_path / "does" / "not" / "exist"

    save_parquet({"wells": pd.DataFrame({"api_number": ["1"]})}, processed_dir)

    assert processed_dir.exists()
