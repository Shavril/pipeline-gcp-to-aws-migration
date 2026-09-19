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


def build_district_lookup_sql(project: str, dataset: str, table: str = "rrc_districts") -> str:
    """Build a CREATE OR REPLACE TABLE statement for the district code/name lookup.

    Small and static enough to inline as literal rows rather than staging
    through Parquet/GCS like the other analytics tables.
    """
    rows = ",\n".join(
        f"    STRUCT('{code}' AS district_code, '{district_id}' AS rrc_district_id, "
        f"'{DISTRICT_NAME_BY_ID[district_id]}' AS district_name)"
        for code, district_id in sorted(DISTRICT_ID_BY_CODE.items())
    )
    return f"""CREATE OR REPLACE TABLE `{project}.{dataset}.{table}` AS
SELECT * FROM UNNEST([
{rows}
])"""
