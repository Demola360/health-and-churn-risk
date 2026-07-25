"""
Loads market_data.csv into BigQuery, and only that table. Kept separate
from load_to_bigquery.py deliberately: the client/login/ticket tables are
synthetic with date patterns baked in at generation time, and shouldn't be
regenerated or reloaded on a schedule. Only live market data should refresh
automatically.

Run with:
    python load_market_data.py

Requires the same environment variables as load_to_bigquery.py:
    GCP_PROJECT_ID, BQ_DATASET
"""

import os
import pandas as pd
from google.cloud import bigquery

REQUIRED_ENV_VARS = ["GCP_PROJECT_ID", "BQ_DATASET"]
CSV_PATH = "market_data.csv"
TABLE_NAME = "market_data"


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
    print(f"Refreshed {table.num_rows} rows -> {table_id}")
