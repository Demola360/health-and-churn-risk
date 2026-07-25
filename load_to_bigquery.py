"""
Day 1 - Step 3: Load into Google BigQuery (Sandbox)
Loads market_data.csv, clients.csv, login_activity.csv and support_tickets.csv
into BigQuery tables using the free Sandbox — no credit card, no billing
account required.

Before running:
  1. Go to https://console.cloud.google.com/bigquery and sign in with a
     Google account. Create a new project (any name, e.g. "client-retention").
     Sandbox mode activates automatically — do NOT add a billing account.
  2. Create a dataset in the BigQuery console (or let this script create it):
     dataset name suggestion: client_retention
  3. Install the Google Cloud CLI and run `gcloud auth application-default
     login` OR download a service account JSON key from IAM & Admin and set
     GOOGLE_APPLICATION_CREDENTIALS to its path. The auth login approach is
     simplest for a solo portfolio project.
  4. Set the environment variables below.
  5. Run fetch_market_data.py and generate_client_data.py first so the CSVs exist.

Note: Sandbox tables auto-expire after 60 days by default. That's fine for
a portfolio project you're actively building, but re-run the pipeline if
you come back to it after a long gap.
"""

import os
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

REQUIRED_ENV_VARS = ["GCP_PROJECT_ID", "BQ_DATASET"]

TABLES = {
    "market_data": "market_data.csv",
    "clients": "clients.csv",
    "login_activity": "login_activity.csv",
    "support_tickets": "support_tickets.csv",
}


def get_client() -> bigquery.Client:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {missing}. "
            "Set these before running (see README.md)."
        )
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def ensure_dataset(client: bigquery.Client, dataset_id: str):
    # Only treat "dataset doesn't exist" as create-it-then. Any other error
    # (auth failure, permission denied, network issue) should surface as
    # itself rather than being silently reinterpreted as a missing dataset.
    full_id = f"{client.project}.{dataset_id}"
    try:
        client.get_dataset(full_id)
    except NotFound:
        print(f"Dataset {full_id} not found, creating it...")
        dataset = bigquery.Dataset(full_id)
        dataset.location = "US"
        client.create_dataset(dataset)


def load_table(client: bigquery.Client, dataset_id: str, table_name: str, csv_path: str):
    df = pd.read_csv(csv_path)
    table_id = f"{client.project}.{dataset_id}.{table_name}"

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # wait for completion

    table = client.get_table(table_id)
    print(f"{table_name}: loaded {table.num_rows} rows -> {table_id}")


if __name__ == "__main__":
    client = get_client()
    dataset_id = os.environ["BQ_DATASET"]
    ensure_dataset(client, dataset_id)

    for table_name, csv_path in TABLES.items():
        load_table(client, dataset_id, table_name, csv_path)

    print("\nDone. Next step (Day 3-4): build the SQL layer — 7-day/30-day")
    print("rolling risk CTEs on top of these raw tables.")
