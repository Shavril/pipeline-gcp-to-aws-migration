import pytest

from oil_pipeline.transform.star_schema import STAR_SCHEMA_DEFINITIONS, build_star_schema_table_sql


@pytest.mark.parametrize("table_name", list(STAR_SCHEMA_DEFINITIONS))
def test_build_star_schema_table_sql_leaves_no_unfilled_placeholders(table_name):
    sql = build_star_schema_table_sql(schema="ds", table_name=table_name)

    assert f"TRUNCATE TABLE ds.{table_name}" in sql
    assert f"INSERT INTO ds.{table_name}" in sql
    assert "{" not in sql and "}" not in sql


def test_dim_lease_references_district_and_operator_natural_keys():
    sql = build_star_schema_table_sql(schema="ds", table_name="dim_lease")

    assert "district_code" in sql
    assert "operator_number" in sql


def test_dim_well_carries_its_own_district_code():
    """dim_well.district_code must not depend on a dim_lease join -- see
    docs/star_schema.md's "Known approximations" (120 wells have no
    matching dim_lease row at all)."""
    sql = build_star_schema_table_sql(schema="ds", table_name="dim_well")

    assert "district_code" in sql


def test_fact_oil_production_references_lease_and_date_natural_keys():
    sql = build_star_schema_table_sql(schema="ds", table_name="fact_oil_production")

    assert "lease_id" in sql
    assert "report_month" in sql


def test_build_star_schema_table_sql_unknown_table_raises():
    with pytest.raises(KeyError):
        build_star_schema_table_sql(schema="ds", table_name="nonexistent_table")
