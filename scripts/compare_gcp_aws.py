"""Prints a GCP (BigQuery) vs AWS (Redshift) validation table.

Runs the checks in gcp_aws_validation_queries.py against both warehouses and
prints the row counts/totals side by side. See docs/validation.md for the
approach and an example run.

Needs a working AWS connection (see oil_pipeline.config.Settings, same as
the rest of the pipeline) and BigQuery access to the reference project (the
standard Google credential chain, e.g. `gcloud auth application-default
login`), plus OIL_PIPELINE_GCP_PROJECT_ID / OIL_PIPELINE_BQ_DATASET set in
.env. Install the extra client library first, since it isn't part of the
pipeline's own dependencies:

    uv sync --group validation
    uv run python scripts/compare_gcp_aws.py
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

import boto3
from gcp_aws_validation_queries import BY_OPERATOR_QUERY_TEMPLATE, CHECKS, build_count_sum_query
from google.cloud import bigquery
from pydantic_settings import BaseSettings, SettingsConfigDict

from oil_pipeline.config import Settings, get_settings

_POLL_INTERVAL_SECONDS = 1.0

# Totals come back through two different numeric paths (Redshift's Data API
# stringifies NUMERIC sums to preserve precision, BigQuery's client returns a
# native int/float) - guard against float round-tripping.
_TOTAL_TOLERANCE = 0.5


class GCPReferenceSettings(BaseSettings):
    """The reference BigQuery project/dataset (texas-oil-data-platform) this script reads.

    Separate from oil_pipeline.config.Settings: only needed to run this
    script, not by the pipeline itself.
    """

    model_config = SettingsConfigDict(env_prefix="OIL_PIPELINE_", env_file=".env", extra="ignore")

    gcp_project_id: str
    bq_dataset: str


@lru_cache
def _get_gcp_reference_settings() -> GCPReferenceSettings:
    return GCPReferenceSettings()


@dataclass(frozen=True)
class CheckResult:
    name: str
    gcp_row_count: int | None
    aws_row_count: int | None
    gcp_total: float | None
    aws_total: float | None

    @property
    def rows_match(self) -> bool:
        return self.gcp_row_count == self.aws_row_count

    @property
    def totals_match(self) -> bool:
        if self.gcp_total is None and self.aws_total is None:
            return True
        if self.gcp_total is None or self.aws_total is None:
            return False
        return abs(self.gcp_total - self.aws_total) <= _TOTAL_TOLERANCE


def _as_int(value: object) -> int | None:
    assert value is None or isinstance(value, int | float | str)
    return None if value is None else int(value)


def _as_float(value: object) -> float | None:
    assert value is None or isinstance(value, int | float | str)
    return None if value is None else float(value)


def _extract_field_value(field: Mapping[str, object]) -> object:
    if field.get("isNull"):
        return None
    for key in ("longValue", "doubleValue", "stringValue", "booleanValue"):
        if key in field:
            return field[key]
    return None


def _fetch_redshift_row(sql: str, workgroup: str, database: str) -> dict[str, object]:
    """Run a SELECT expected to return exactly one row, as a dict of column name to value.

    Only meant for the small aggregate queries this script runs (a
    COUNT/SUM) - not a general, paginated result fetcher.
    """
    client = boto3.client("redshift-data")
    response = client.execute_statement(WorkgroupName=workgroup, Database=database, Sql=sql)
    statement_id = response["Id"]
    while True:
        status_response = client.describe_statement(Id=statement_id)
        status = status_response["Status"]
        if status == "FINISHED":
            break
        if status in ("FAILED", "ABORTED"):
            raise RuntimeError(f"Redshift statement {status}: {status_response.get('Error')}")
        time.sleep(_POLL_INTERVAL_SECONDS)

    result = client.get_statement_result(Id=statement_id)
    columns = [column["name"] for column in result["ColumnMetadata"]]
    row = result["Records"][0]
    return {name: _extract_field_value(field) for name, field in zip(columns, row, strict=True)}


def _fetch_bigquery_row(client: bigquery.Client, sql: str) -> dict[str, object]:
    rows = list(client.query(sql).result())
    return dict(rows[0])


def _bigquery_table_ref(gcp_settings: GCPReferenceSettings, table: str) -> str:
    return f"`{gcp_settings.gcp_project_id}.{gcp_settings.bq_dataset}.{table}`"


def _redshift_table_ref(settings: Settings, table: str) -> str:
    return f"{settings.redshift_schema}.{table}"


def _to_result(name: str, gcp_row: dict[str, object], aws_row: dict[str, object]) -> CheckResult:
    return CheckResult(
        name=name,
        gcp_row_count=_as_int(gcp_row["row_count"]),
        aws_row_count=_as_int(aws_row["row_count"]),
        gcp_total=_as_float(gcp_row["total"]),
        aws_total=_as_float(aws_row["total"]),
    )


def run_checks(settings: Settings, gcp_settings: GCPReferenceSettings) -> list[CheckResult]:
    """Run every check in CHECKS, plus the ad hoc by-operator check, against both warehouses."""
    bq_client = bigquery.Client(project=gcp_settings.gcp_project_id)
    results = []

    for check in CHECKS:
        aws_sql = build_count_sum_query(_redshift_table_ref(settings, check.table), check.sum_column)
        gcp_sql = build_count_sum_query(_bigquery_table_ref(gcp_settings, check.table), check.sum_column)

        aws_row = _fetch_redshift_row(aws_sql, settings.redshift_workgroup_name, settings.redshift_database_name)
        gcp_row = _fetch_bigquery_row(bq_client, gcp_sql)
        results.append(_to_result(check.name, gcp_row, aws_row))

    aws_operator_sql = BY_OPERATOR_QUERY_TEMPLATE.format(
        fact_table=_redshift_table_ref(settings, "fact_oil_production"),
        dim_lease_table=_redshift_table_ref(settings, "dim_lease"),
    )
    gcp_operator_sql = BY_OPERATOR_QUERY_TEMPLATE.format(
        fact_table=_bigquery_table_ref(gcp_settings, "fact_oil_production"),
        dim_lease_table=_bigquery_table_ref(gcp_settings, "dim_lease"),
    )
    aws_row = _fetch_redshift_row(aws_operator_sql, settings.redshift_workgroup_name, settings.redshift_database_name)
    gcp_row = _fetch_bigquery_row(bq_client, gcp_operator_sql)
    results.append(_to_result("total_oil_production_by_operator", gcp_row, aws_row))

    return results


def format_table(results: list[CheckResult]) -> str:
    """Render the results as a plain-text, aligned, side-by-side table."""
    headers = ["Check", "GCP rows", "AWS rows", "Rows", "GCP total", "AWS total", "Total"]

    def fmt_int(value: int | None) -> str:
        return "-" if value is None else f"{value:,}"

    def fmt_float(value: float | None) -> str:
        return "-" if value is None else f"{value:,.0f}"

    body = [
        [
            r.name,
            fmt_int(r.gcp_row_count),
            fmt_int(r.aws_row_count),
            "MATCH" if r.rows_match else "MISMATCH",
            fmt_float(r.gcp_total),
            fmt_float(r.aws_total),
            "MATCH" if r.totals_match else "MISMATCH",
        ]
        for r in results
    ]

    widths = [max(len(str(row[i])) for row in [headers, *body]) for i in range(len(headers))]
    lines = [
        " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(headers)),
        "-+-".join("-" * w for w in widths),
    ]
    lines.extend(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) for row in body)
    return "\n".join(lines)


def main() -> None:
    settings = get_settings()
    gcp_settings = _get_gcp_reference_settings()
    results = run_checks(settings, gcp_settings)

    print(format_table(results))

    mismatches = [r for r in results if not (r.rows_match and r.totals_match)]
    if mismatches:
        print(f"\n{len(mismatches)} check(s) mismatched: {', '.join(r.name for r in mismatches)}")
    else:
        print("\nAll checks match.")


if __name__ == "__main__":
    main()
