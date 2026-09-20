"""RRC district code/name reference data, shared across analytics tables."""

# PD-OIL-DISTRICT stored value -> public-facing RRC district ID (docs/data_rrc_production.md)
DISTRICT_ID_BY_CODE = {
    "01": "1",
    "02": "2",
    "03": "3",
    "04": "4",
    "05": "5",
    "06": "6",
    "07": "6E",
    "08": "7B",
    "09": "7C",
    "10": "8",
    "11": "8A",
    "12": "8B",
    "13": "9",
    "14": "10",
}

# Informal/commonly used regional names for each RRC district. NOT an official
# RRC designation — RRC districts have no official names, only these numeric/
# alphanumeric codes. Best-effort industry-common shorthand, not sourced from
# any RRC data file and not independently verified.
DISTRICT_NAME_BY_ID = {
    "1": "South Texas",
    "2": "Coastal Bend",
    "3": "Gulf Coast",
    "4": "South Texas",
    "5": "North-Central Texas",
    "6": "East Texas",
    "6E": "East Texas East",
    "7B": "Eastern Permian",
    "7C": "Central Permian",
    "8": "Permian Basin",
    "8A": "Northern Permian",
    "8B": "RESERVED",
    "9": "North Texas",
    "10": "Panhandle",
}


def build_district_lookup_sql(schema: str, table: str = "rrc_districts") -> str:
    """Build DROP + CREATE TABLE AS SELECT statements for the district code/name lookup.

    Small and static enough to inline as literal rows rather than staging
    through Parquet/S3 like the other analytics tables. Redshift has no
    CREATE OR REPLACE TABLE, so this is DROP IF EXISTS + CREATE AS SELECT
    rather than one statement.

    Uses UNION ALL of single-row SELECTs, not a `VALUES (...), (...)` table
    constructor -- the ltter fails with a syntax error at the second row (Redshift's
    parser only accepts one row there, unlike Postgres/BigQuery).
    """
    rows = "\nUNION ALL\n".join(
        f"SELECT '{code}' AS district_code, '{district_id}' AS rrc_district_id, "
        f"'{DISTRICT_NAME_BY_ID[district_id]}' AS district_name"
        for code, district_id in sorted(DISTRICT_ID_BY_CODE.items())
    )
    qualified_table = f"{schema}.{table}"
    return f"""DROP TABLE IF EXISTS {qualified_table};
CREATE TABLE {qualified_table} AS
{rows}"""
