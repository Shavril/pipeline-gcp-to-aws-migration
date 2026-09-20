from oil_pipeline.transform.districts import (
    DISTRICT_ID_BY_CODE,
    DISTRICT_NAME_BY_ID,
    build_district_lookup_sql,
)


def test_every_district_code_maps_to_a_named_district():
    for district_id in DISTRICT_ID_BY_CODE.values():
        assert district_id in DISTRICT_NAME_BY_ID


def test_build_district_lookup_sql_includes_every_district():
    sql = build_district_lookup_sql(schema="ds")

    assert "DROP TABLE IF EXISTS ds.rrc_districts" in sql
    assert "CREATE TABLE ds.rrc_districts AS" in sql
    for code, district_id in DISTRICT_ID_BY_CODE.items():
        assert f"SELECT '{code}' AS district_code, '{district_id}' AS rrc_district_id" in sql


def test_build_district_lookup_sql_custom_table_name():
    sql = build_district_lookup_sql(schema="ds", table="custom_districts")

    assert "ds.custom_districts" in sql
