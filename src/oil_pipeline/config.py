"""Central pipeline configuration.

Every field is required -- it must come from an
OIL_PIPELINE_-prefixed environment variable or a .env file at the repo
root (see .env.example, gitignored once copied to .env). Settings() raises
a validation error listing exactly which ones are missing if it isn't set
up yet.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OIL_PIPELINE_", env_file=".env", extra="ignore")

    raw_production_path: Path
    raw_p4_path: Path
    raw_p5_path: Path
    raw_wells_path: Path
    # One DuckDB file per independent pipeline line (not one shared file) --
    # DuckDB allows only one writer per file, and Dagster gives no ordering
    # guarantee between assets that don't have a real data dependency (e.g.
    # p4_raw and p5_raw, both feeding lease_operators). Splitting the file
    # per line removes the contention structurally instead of relying on a
    # specific executor's scheduling behavior to avoid it.
    oil_production_db_path: Path
    lease_operators_db_path: Path
    wells_db_path: Path
    processed_data_path: Path

    gcp_project_id: str
    gcs_bucket_name: str
    bq_dataset: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
