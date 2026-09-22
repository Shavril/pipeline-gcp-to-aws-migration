# Validating the migration: GCP vs AWS

The original GCP project (`texas-oil-data-platform`, BigQuery) is treated as the reference
implementation. This project's AWS output (Redshift) is checked against it.

## Approach

Both projects build the same star schema (`dim_date`, `dim_district`, `dim_operator`,
`dim_lease`, `dim_well`, `fact_oil_production` — full model, grain, and key reasoning in the
original project's [`docs/star_schema.md`](https://github.com/Shavril/texas-oil-data-platform/blob/main/docs/star_schema.md))
and the same set of analytical views
(`total_oil_production_by_lease_id_view`, `total_oil_production_by_month_and_district_code_view`,
`total_oil_production_by_month_and_county_view`, `wells_view`, `oil_production_violations_view`)
from identical business logic, so the same query pointed at each warehouse's own copy of a
same-named table or view should return the same row count and total.

`scripts/compare_gcp_aws.py` (checks defined in `scripts/gcp_aws_validation_queries.py`) runs
a `COUNT(*)` + `SUM(...)` check against BigQuery and Redshift for each of the following, and
prints the two sides next to each other:

- `fact_oil_production` (raw grain) - total row count and total oil production
- `total_oil_production_by_lease_id_view` - production rolled up by lease
- `total_oil_production_by_month_and_district_code_view` - production by month and district
- `total_oil_production_by_month_and_county_view` - production by month and county
- `wells_view` - well count and total well depth, as an independent (non-production) check
- `total_oil_production_by_operator` - an ad hoc aggregate joining `fact_oil_production` 
  to `dim_lease`, grouped by operator

"Production by field" is not included - neither project's analytical model tracks a "field"
concept, only district/county/lease/well/operator, so there is nothing to compare there.

Because both warehouses only agree if they were loaded from the same underlying data, this
is a live comparison (querying both warehouses each run), not a check against a fixed
expected value. 

SQL dialect differences that came up porting the Redshift-facing SQL from BigQuery are
documented in the main [`README.md`](../README.md#architectural-decisions), under
Architectural decisions.

## Running it

Needs a working AWS connection (the same one the pipeline itself uses) and BigQuery access
to the reference project (the standard Google credential chain, e.g.
`gcloud auth application-default login`), plus `OIL_PIPELINE_GCP_PROJECT_ID` and
`OIL_PIPELINE_BQ_DATASET` set in `.env` (see `.env.example`). The BigQuery client is only
needed for this script, not for the pipeline itself, so it lives in its own dependency
group:

```
uv sync --group validation
uv run python scripts/compare_gcp_aws.py
```

## Latest run

Run on 2026-09-22, both warehouses loaded from the same pipeline output:

```
Check                                                | GCP rows  | AWS rows  | Rows  | GCP total     | AWS total     | Total
-----------------------------------------------------+-----------+-----------+-------+---------------+---------------+------
fact_oil_production (raw grain)                      | 1,625,955 | 1,625,955 | MATCH | 2,978,117,307 | 2,978,117,307 | MATCH
total_oil_production_by_lease_id_view                | 73,680    | 73,680    | MATCH | 2,978,117,307 | 2,978,117,307 | MATCH
total_oil_production_by_month_and_district_code_view | 312       | 312       | MATCH | 2,978,117,307 | 2,978,117,307 | MATCH
total_oil_production_by_month_and_county_view        | 14,244    | 14,244    | MATCH | 2,978,117,307 | 2,978,117,307 | MATCH
wells_view                                           | 623,014   | 623,014   | MATCH | 2,766,230,335 | 2,766,230,335 | MATCH
total_oil_production_by_operator                     | 3,639     | 3,639     | MATCH | 2,978,117,307 | 2,978,117,307 | MATCH

All checks match.
```

Every check matched exactly, confirming the migration
preserved the analytical model's results, not just its ability to run.
