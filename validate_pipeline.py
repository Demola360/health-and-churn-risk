"""
Lightweight data-quality validation for the pipeline.

Runs a set of SQL assertions against BigQuery and reports pass/fail for
each. Exits with a non-zero status code if any check fails, so this can
plug into GitHub Actions later without changes.

Run with:
    python validate_pipeline.py

Requires the same environment variables as load_to_bigquery.py:
    set GCP_PROJECT_ID=health-and-churn-risk
    set BQ_DATASET=client_retention
"""

import os
import sys
from google.cloud import bigquery

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
DATASET = os.environ.get("BQ_DATASET")

if not PROJECT_ID or not DATASET:
    raise EnvironmentError("Set GCP_PROJECT_ID and BQ_DATASET before running.")

client = bigquery.Client(project=PROJECT_ID)


def run_check(name: str, query: str, expect_zero: bool = True) -> bool:
    result = list(client.query(query).result())
    value = result[0][0] if result else None

    passed = (value == 0) if expect_zero else (value is not None and value > 0)
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name} (value={value})")
    return passed


checks = [
    (
        "clients table has rows",
        f"SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.clients`",
        False,
    ),
    (
        "market_data table has rows",
        f"SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.market_data`",
        False,
    ),
    (
        "login_activity table has rows",
        f"SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.login_activity`",
        False,
    ),
    (
        "support_tickets table has rows",
        f"SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.support_tickets`",
        False,
    ),
    (
        "no duplicate client_id in clients",
        f"""
        SELECT COUNT(*) FROM (
          SELECT client_id FROM `{PROJECT_ID}.{DATASET}.clients`
          GROUP BY client_id HAVING COUNT(*) > 1
        )
        """,
        True,
    ),
    (
        "no null client_id in clients",
        f"SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.clients` WHERE client_id IS NULL",
        True,
    ),
    (
        "login_activity has no orphaned client_ids",
        f"""
        SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.login_activity` l
        LEFT JOIN `{PROJECT_ID}.{DATASET}.clients` c USING (client_id)
        WHERE c.client_id IS NULL
        """,
        True,
    ),
    (
        "support_tickets has no orphaned client_ids",
        f"""
        SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.support_tickets` t
        LEFT JOIN `{PROJECT_ID}.{DATASET}.clients` c USING (client_id)
        WHERE c.client_id IS NULL
        """,
        True,
    ),
    (
        "no negative policy values",
        f"SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.clients` WHERE policy_value_gbp < 0",
        True,
    ),
    (
        "risk_score is within 0-100",
        f"""
        SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.client_risk_final`
        WHERE risk_score < 0 OR risk_score > 100
        """,
        True,
    ),
    (
        "risk_tier only has expected values",
        f"""
        SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.client_risk_final`
        WHERE risk_tier NOT IN ('Low', 'Medium', 'High')
        """,
        True,
    ),
    (
        "renewal_status only has expected values",
        f"""
        SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.client_risk_final`
        WHERE renewal_status NOT IN ('Lapsed', 'Renewal due soon', 'Upcoming')
        """,
        True,
    ),
    (
        "every client in clients has a row in client_risk_final",
        f"""
        SELECT COUNT(*) FROM `{PROJECT_ID}.{DATASET}.clients` c
        LEFT JOIN `{PROJECT_ID}.{DATASET}.client_risk_final` f USING (client_id)
        WHERE f.client_id IS NULL
        """,
        True,
    ),
]

if __name__ == "__main__":
    results = [run_check(name, query, expect_zero) for name, query, expect_zero in checks]

    passed_count = sum(results)
    total_count = len(results)
    print(f"\n{passed_count}/{total_count} checks passed")

    if passed_count < total_count:
        sys.exit(1)
