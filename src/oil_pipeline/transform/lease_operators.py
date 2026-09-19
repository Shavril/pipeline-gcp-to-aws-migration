"""Build the lease_operators analytics table by joining P-4 leases to P-5 organizations."""

from pathlib import Path

import duckdb
import pandas as pd


def build_lease_operators(db_path: Path) -> pd.DataFrame:
    """Join P-4 Root (oil leases only) to P-5 Organization on operator_number.

    Grain: one row per oil lease (district_code, lease_nbr). P-4 Root also
    contains gas wells (oil_gas_code = 'G') — filtered out here, since the
    production tape is oil-only and a gas well could otherwise coincidentally
    share a (district_code, lease_nbr) with an oil lease (see
    docs/data_p4_operators.md Known Issues).

    P-4 Root is also confirmed to contain exact duplicate records for the
    same (oil_gas_code, district_code, lease_nbr) on real data (byte-
    identical, same operator_number) — a genuine tape quirk, not a decode
    bug. Deduped defensively here (one row per lease, lowest operator_number
    if they ever differ) to guarantee the grain regardless, same technique
    as transform/wells.py's completion/new_location dedup.

    LEFT JOIN to P-5 so a lease whose operator number has no matching P-5
    organization record surfaces as a null organization_name rather than
    silently dropping the lease.
    """
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute("""
            WITH p4_oil_dedup AS (
                SELECT
                    district_code,
                    lease_nbr,
                    operator_number,
                    ROW_NUMBER() OVER (
                        PARTITION BY district_code, lease_nbr
                        ORDER BY operator_number
                    ) AS rn
                FROM p4_root
                WHERE oil_gas_code = 'O'
            ),
            p4_oil AS (
                SELECT district_code, lease_nbr, operator_number
                FROM p4_oil_dedup
                WHERE rn = 1
            )
            SELECT
                p4.district_code,
                p4.lease_nbr,
                CONCAT(p4.district_code, '-', p4.lease_nbr) AS lease_id,
                p4.operator_number,
                p5.organization_name,
                p5.p5_status
            FROM p4_oil p4
            LEFT JOIN p5_organizations p5
              ON p4.operator_number = p5.operator_number
        """).fetchdf()

    return df
