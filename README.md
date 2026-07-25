# Client Health & Churn Risk Dashboard

Portfolio project simulating a predictive client retention engine for a
financial-services book of business. Combines live banking-sector market
data (as a "market stress" proxy) with simulated client behavioural data
(logins, support tickets, renewal dates) to surface churn risk.

**Data honesty note:** the client-level data (logins, tickets, renewals) is
synthetic, generated with deliberately realistic risk patterns so the model
has genuine signal to find. This is stated plainly in the dashboard footer
and in any write-up or interview discussion of this project — it is not
presented as real client data. The market data (banking sector tickers) is
real, pulled live via yfinance.

## Stack
- **Python/pandas** — data generation and transformation
- **yfinance** — live banking-sector market data (8 tickers: JPM, BAC, WFC,
  C, GS, MS, HSBC, BCS)
- **Google BigQuery (Sandbox)** — data warehouse, free, no credit card
- **GitHub Actions** — scheduled pipeline runs
- **Streamlit** — dashboard front end

## Day 1-2: Pipeline setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up BigQuery (no credit card needed)
1. Go to https://console.cloud.google.com/bigquery and sign in with a Google account.
2. Create a new project (any name, e.g. `client-retention`). Sandbox mode
   activates automatically as long as you don't add a billing account.
3. Authenticate locally so the pipeline can write to it:
   ```bash
   gcloud auth application-default login
   ```
   (Install the Google Cloud CLI first if you don't have it:
   https://cloud.google.com/sdk/docs/install)
4. Set environment variables:
   ```bash
   export GCP_PROJECT_ID="your-project-id"
   export BQ_DATASET="client_retention"
   ```

### 3. Run the pipeline, in order
```bash
python fetch_market_data.py       # -> market_data.csv
python generate_client_data.py    # -> clients.csv, login_activity.csv, support_tickets.csv
python load_to_bigquery.py        # creates the dataset (if needed) and loads all CSVs
```

### 4. Verify
In the BigQuery console, check row counts:
```sql
SELECT COUNT(*) FROM `client_retention.market_data`;
SELECT COUNT(*) FROM `client_retention.clients`;
SELECT COUNT(*) FROM `client_retention.login_activity`;
SELECT COUNT(*) FROM `client_retention.support_tickets`;
```

**Note:** Sandbox tables auto-expire after 60 days by default — fine while
you're actively building, just re-run the pipeline if you pick this back up
after a long break.

## What's next (Day 3-4, Day 5)
- **SQL layer:** 7-day/30-day rolling risk CTEs on top of these raw tables
  (login frequency trend, ticket volume trend, days-to-renewal, market
  volatility join)
- **Streamlit dashboard:** client-level risk scores, a portfolio-level risk
  heatmap, and drill-down into the signals driving each score
- **GitHub Actions:** schedule `fetch_market_data.py` to run daily so market
  data stays current

## Files
| File | Purpose |
|---|---|
| `fetch_market_data.py` | Pulls live OHLCV data for 8 banking tickers |
| `generate_client_data.py` | Generates simulated client/login/ticket data |
| `load_to_bigquery.py` | Loads all CSVs into BigQuery tables |
| `requirements.txt` | Python dependencies |
