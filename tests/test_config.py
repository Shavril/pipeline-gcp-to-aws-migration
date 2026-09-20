from pathlib import Path

import pytest
from pydantic import ValidationError

from oil_pipeline.config import Settings, get_settings

REQUIRED_ENV = {
    "OIL_PIPELINE_RAW_PRODUCTION_PATH": "data/raw/production/PDF100.ebc",
    "OIL_PIPELINE_RAW_P4_PATH": "data/raw/operators/p4f606.ebc",
    "OIL_PIPELINE_RAW_P5_PATH": "data/raw/organizations/orf850.ebc",
    "OIL_PIPELINE_RAW_WELLS_PATH": "data/raw/wells/dbf900.ebc",
    "OIL_PIPELINE_OIL_PRODUCTION_DB_PATH": "data/database/oil_production.duckdb",
    "OIL_PIPELINE_LEASE_OPERATORS_DB_PATH": "data/database/lease_operators.duckdb",
    "OIL_PIPELINE_WELLS_DB_PATH": "data/database/wells.duckdb",
    "OIL_PIPELINE_PROCESSED_DATA_PATH": "data/processed",
    "OIL_PIPELINE_AWS_REGION": "us-east-1",
    "OIL_PIPELINE_S3_BUCKET_NAME": "pipeline-gcp-to-aws-migration",
    "OIL_PIPELINE_REDSHIFT_WORKGROUP_NAME": "pipeline-gcp-to-aws-migration",
    "OIL_PIPELINE_REDSHIFT_DATABASE_NAME": "dev",
    "OIL_PIPELINE_REDSHIFT_SCHEMA": "analytics",
    "OIL_PIPELINE_REDSHIFT_S3_ROLE_ARN": "arn:aws:iam::740948698458:role/redshift-s3-read",
}


@pytest.fixture
def all_required_env(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def test_settings_load_from_env_vars(all_required_env):
    settings = Settings(_env_file=None)

    assert settings.raw_production_path == Path("data/raw/production/PDF100.ebc")
    assert settings.s3_bucket_name == "pipeline-gcp-to-aws-migration"
    assert settings.redshift_schema == "analytics"


def test_settings_override(all_required_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OIL_PIPELINE_REDSHIFT_SCHEMA", "some_other_schema")
    monkeypatch.setenv("OIL_PIPELINE_WELLS_DB_PATH", "/tmp/custom_wells.duckdb")

    settings = Settings(_env_file=None)

    assert settings.redshift_schema == "some_other_schema"
    assert settings.wells_db_path == Path("/tmp/custom_wells.duckdb")


def test_settings_missing_required_field_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached(all_required_env):
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
