"""
Loads clients_risk_segment_ANSWER_KEY.csv into its own BigQuery table,
kept deliberately separate from load_to_bigquery.py.

This table exists ONLY for the sanity-check query at the bottom of
risk_layer.sql — comparing the rule-based risk_tier against the hidden
risk_segment used to generate the synthetic data. It is never joined into
client_risk_scores or client_risk_final, and the dashboard never queries it.

Run this after load_to_bigquery.py, once, whenever you want to re-validate
the scoring logic against the synthetic ground truth:
    python load_answer_key.py
"""

import os
import pandas as pd
from google.cloud import bigquery

REQUIRED_ENV_VARS = ["GCP_PROJECT_ID", "BQ_DATASET"]
CSV_PATH = "clients_risk_segment_ANSWER_KEY.csv"
TABLE_NAME = "clients_risk_segment_answer_key"


def get_client() -> bigquery.Client:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {missing}")
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


if __name__ == "__main__":
    client = get_client()
    dataset_id = os.environ["BQ_DATASET"]

    df = pd.read_csv(CSV_PATH)
    table_id = f"{client.project}.{dataset_id}.{TABLE_NAME}"

    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()

    table = client.get_table(table_id)
    print(f"Loaded {table.num_rows} rows -> {table_id}")
    print("This table is validation-only — never referenced by app.py or client_risk_final.")
