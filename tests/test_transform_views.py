import pytest

from oil_pipeline.transform.views import VIEW_DEFINITIONS, build_view_sql


@pytest.mark.parametrize("view_name", list(VIEW_DEFINITIONS))
def test_build_view_sql_leaves_no_unfilled_placeholders(view_name):
    sql = build_view_sql(schema="ds", view_name=view_name)

    assert f"CREATE OR REPLACE VIEW ds.{view_name}" in sql
    assert "{" not in sql and "}" not in sql


def test_build_view_sql_uses_the_view_own_source_table_by_default():
    sql = build_view_sql(schema="ds", view_name="wells_view")

    assert "ds.dim_well" in sql


def test_build_view_sql_source_table_override():
    sql = build_view_sql(schema="ds", view_name="wells_view", source_table="dim_well_v2")

    assert "ds.dim_well_v2" in sql
    assert "FROM ds.dim_well dw" not in sql


def test_build_view_sql_unknown_view_raises():
    with pytest.raises(KeyError):
        build_view_sql(schema="ds", view_name="nonexistent_view")
