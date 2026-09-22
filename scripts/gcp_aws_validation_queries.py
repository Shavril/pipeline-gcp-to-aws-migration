"""Canonical row-count / total-production checks used by compare_gcp_aws.py.

Both warehouses are built from the same business logic and the same
star-schema table/view names (this project's whole premise), so the same
aggregate query, pointed at each warehouse's own copy of the same-named
table or view, should return the same row count and total.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    table: str
    sum_column: str | None


CHECKS: list[Check] = [
    Check("fact_oil_production (raw grain)", "fact_oil_production", "oil_production_bbl"),
    Check(
        "total_oil_production_by_lease_id_view",
        "total_oil_production_by_lease_id_view",
        "total_oil_production_bbl",
    ),
    Check(
        "total_oil_production_by_month_and_district_code_view",
        "total_oil_production_by_month_and_district_code_view",
        "total_oil_production_bbl",
    ),
    Check(
        "total_oil_production_by_month_and_county_view",
        "total_oil_production_by_month_and_county_view",
        "total_oil_production_bbl",
    ),
    Check("wells_view", "wells_view", "total_depth_ft"),
]

# Not one of the pre-built views (neither project has a by-operator view) -
# grouped ad hoc from the same star-schema tables the by-lease view itself
# joins, so it's still built from identical source data and logic on both
# sides.
BY_OPERATOR_QUERY_TEMPLATE = """
SELECT COUNT(*) AS row_count, SUM(total_bbl) AS total
FROM (
    SELECT dl.operator_number, SUM(f.oil_production_bbl) AS total_bbl
    FROM {fact_table} f
    LEFT JOIN {dim_lease_table} dl ON f.lease_id = dl.lease_id
    GROUP BY dl.operator_number
) t
"""


def build_count_sum_query(table_ref: str, sum_column: str | None) -> str:
    """A COUNT(*) + SUM(sum_column) query against one fully-qualified table or view reference."""
    sum_expr = f"SUM({sum_column}) AS total" if sum_column else "NULL AS total"
    return f"SELECT COUNT(*) AS row_count, {sum_expr} FROM {table_ref}"
