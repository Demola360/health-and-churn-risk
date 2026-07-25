# Development Log: Client Health & Churn Risk Dashboard

*(also referred to as the Predictive Client Retention Engine)*

---

## 1. Project Overview & Final Tech Stack

**What we built:** an end-to-end portfolio project simulating a predictive
client retention engine for a financial-services book of business. It
combines live banking-sector market data with simulated client behavioural
data (logins, support tickets, renewal dates) to score churn risk and
surface it in an interactive dashboard.

**Approach:** build fast first with AI assistance, then go back and study
the code to understand it deeply — the reverse of the usual "learn theory,
then build" order.

**Final stack:**

| Layer | Tool | Purpose |
|---|---|---|
| Market data | `yfinance` | Pulls live OHLCV data for 8 banking-sector tickers as a "market stress" proxy |
| Simulated data | `pandas` / `numpy` | Generates realistic synthetic client login, ticket, and renewal data |
| Warehouse | Google BigQuery (Sandbox) | Free, no-card SQL data warehouse |
| Transformation | BigQuery SQL (views) | Rolling risk signals, combined into a 0–100 risk score |
| Dashboard | Streamlit | Interactive front end reading directly from BigQuery |
| Auth | `gcloud` CLI + Application Default Credentials | Local authentication to BigQuery, no service account key needed |

**Note on data honesty:** the client-level data (logins, tickets, renewals)
is synthetic — generated with deliberately realistic risk patterns so the
model has genuine signal to find. This is stated explicitly in the
dashboard itself, not just this log. The banking-sector market data is
real and pulled live.

---

## 2. Step-by-Step Evolution

### Step 1 — Scoping the project and locking the stack
**Goal:** turn a vague project name into a concrete, buildable plan before
writing any code.

**Logic:** rather than start coding immediately, we fixed the stack, the
sector for market-proxy data (Banking/Finance), and a day-by-day build
sequence up front:

- Day 1–2: data pipeline (market pull + simulated client data), landed in a warehouse
- Day 3–4: SQL layer (rolling risk signals)
- Day 5: Streamlit dashboard
- Following week: review the code and write a one-page summary

This mattered because every later decision (warehouse choice, table
design, view structure) depended on this sequence being fixed early.

---

### Step 2 — Market data pipeline (`fetch_market_data.py`)
**Goal:** pull real, live data for a defensible "market stress" signal.

**Core logic:** loop over 8 major banking tickers (mix of US and UK, since
the target job market is UK-based), pull a year of daily OHLCV data per
ticker, and compute two derived features the SQL layer would need later:

```python
data["daily_return"] = data["Close"].pct_change()
data["volatility_10d"] = data["daily_return"].rolling(10).std()
```

All tickers are concatenated into one tidy long-format table and exported
to `market_data.csv`.

---

### Step 3 — Simulated client data (`generate_client_data.py`)
**Goal:** generate synthetic client behavioural data with genuine risk
signal baked in — not random noise — so a scoring model would have
something real to detect.

**Core logic:** each client is assigned a hidden `risk_segment`
(`high` / `medium` / `low`, 20/30/50% split) that is *not* exposed to the
model. That segment drives the simulated behaviour:

```python
# High-risk clients: login probability decays toward near-zero over time
if client["risk_segment"] == "high":
    decay = max(0.02, p0 * (1 - day_idx / SIM_DAYS))
else:
    decay = p0
```

```python
# High-risk clients: more support tickets, clustered later in the window
if client["risk_segment"] == "high":
    n_tickets = np.random.poisson(6)
else:
    n_tickets = np.random.poisson(0.5)
```

The `risk_segment` "answer key" is exported to a **separate** CSV
(`clients_risk_segment_ANSWER_KEY.csv`) so it can never accidentally leak
into the model as a feature — it exists only to validate scoring logic
later.

---

### Step 4 — Warehouse loader (`load_to_bigquery.py`)
**Goal:** land all four CSVs (market data, clients, logins, tickets) into
BigQuery tables.

**Core logic:** authenticate via the `google-cloud-bigquery` client
library, auto-create the dataset if missing, and load each CSV with schema
autodetection:

```python
job_config = bigquery.LoadJobConfig(
    write_disposition="WRITE_TRUNCATE",
    autodetect=True,
)
job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
```

This step went through a full warehouse pivot — see Mistake #1 below.

---

### Step 5 — SQL risk layer (`risk_layer.sql`)
**Goal:** transform raw event tables into one interpretable risk score per
client.

**Core logic:** five layered views, combined into a final scored view:

1. `login_trend` — 7-day and 30-day login counts, current vs. prior window
2. `ticket_trend` — ticket volume and unresolved-within-SLA counts
3. `renewal_window` — days until each client's renewal date
4. `market_stress` — portfolio-level (not per-client) sector volatility context
5. `client_risk_scores` — combines all signals into a weighted 0–100 score:

```sql
LEAST(100, GREATEST(0,
    (40 * LEAST(1, GREATEST(0, -1 * COALESCE(l.login_change_30d_pct, 0))))
  + (30 * LEAST(1, COALESCE(t.tickets_last_30d, 0) / 6.0))
  + (15 * LEAST(1, COALESCE(t.unresolved_last_30d, 0) / 3.0))
  + (15 * LEAST(1, GREATEST(0, (60 - r.days_to_renewal) / 60.0)))
)) AS risk_score
```

The weighting is a deliberately simple, explainable rule set rather than a
trained model — a transparent baseline to compare a future ML model
against, and something that's easy to walk through in an interview.

`client_risk_final` adds a `risk_tier` (`Low` / `Medium` / `High`) on top
of the numeric score.

---

### Step 6 — Streamlit dashboard (`app.py`)
**Goal:** give the risk scores a usable, explorable front end.

**Core logic:** query `client_risk_final` directly from BigQuery, cache
the result, and build the UI in layers — KPIs, then charts, then a
sortable table, then a client-level drill-down:

```python
@st.cache_data(ttl=600)
def load_risk_data() -> pd.DataFrame:
    client = get_client()
    query = f"SELECT * FROM `{PROJECT_ID}.{DATASET}.client_risk_final`"
    return client.query(query).to_dataframe()
```

Sidebar filters (risk tier, renewal window) drive every element on the
page from one filtered dataframe, so the KPIs, charts, and table always
stay in sync.

---

## 3. Roadmap of Mistakes & Debugging

### Mistake 1 — Snowflake trial required card details
**What went wrong:** Snowflake's documented policy is "no card required"
for the 30-day trial, but the actual sign-up flow you hit demanded card
details anyway.

**Root cause:** sign-up flows vary by region/account type and can diverge
from published policy; also, Snowflake's trial is time-boxed (30 days),
which was a poor fit regardless.

**Fix:** pivoted the entire warehouse layer from Snowflake to **Google
BigQuery Sandbox** — genuinely free, no card, no expiry, equally relevant
on a UK CV. This meant rewriting `load_to_snowflake.py` into
`load_to_bigquery.py` and updating the README and `requirements.txt`
accordingly.

---

### Mistake 2 — `gcloud` not recognized
**What went wrong:**
```
'gcloud' is not recognized as an internal or external command
```

**Root cause:** the Google Cloud CLI wasn't installed yet — `gcloud auth`
was attempted before the tool existed on the machine.

**Fix:** downloaded and ran the Windows Cloud SDK installer, then opened a
**new** terminal window (an already-open one won't pick up the updated
system PATH).

---

### Mistake 3 — Script run from the wrong directory
**What went wrong:**
```
python: can't open file '...\Cloud SDK\fetch_market_data.py': [Errno 2] No such file or directory
```

**Root cause:** the terminal's working directory was wherever `gcloud`
had been installed, not the folder the pipeline scripts were saved to.

**Fix:** `cd` into the actual project folder
(`C:\Users\User\Desktop\health_and_churn_risk`) before running any script.

---

### Mistake 4 — Missing Python packages
**What went wrong:**
```
ModuleNotFoundError: No module named 'yfinance'
ModuleNotFoundError: No module named 'google.cloud'
```

**Root cause:** `pip install -r requirements.txt` was never run in the
project folder — the scripts existed, but their dependencies didn't.

**Fix:** `pip install -r requirements.txt` (or `python -m pip install ...`
if `pip` itself isn't recognized).

---

### Mistake 5 — Missing environment variables
**What went wrong:**
```
OSError: Missing required environment variables: ['GCP_PROJECT_ID', 'BQ_DATASET']
```

**Root cause:** the `export VAR=value` syntax used in the README is
**bash** syntax; this was a Windows CMD session, which needs `set`
instead. CMD environment variables also don't persist across terminal
sessions — they must be re-set every time a new window is opened.

**Fix:**
```
set GCP_PROJECT_ID=health-and-churn-risk
set BQ_DATASET=client_retention
```
run in the same window, immediately before the script.

---

### Mistake 6 — Application Default Credentials missing
**What went wrong:**
```
google.auth.exceptions.DefaultCredentialsError: Your default credentials were not found.
```

**Root cause:** `gcloud init` authenticates the **CLI tool** itself, but
the `google-cloud-bigquery` **Python library** looks for a separate
credential store ("Application Default Credentials"). Logging into gcloud
does not automatically satisfy this.

**Fix:**
```
gcloud auth application-default login
```
run as a distinct step, in addition to the initial `gcloud init` login.

---

### Mistake 7 — STRING vs. DATE type mismatch in SQL
**What went wrong:**
```
No matching signature for operator >= for argument types: STRING, DATE
```

**Root cause:** when the CSVs were loaded with BigQuery's schema
`autodetect=True`, date columns (`login_date`, `ticket_date`,
`renewal_date`, `trade_date`) were inferred as `STRING` rather than
`DATE` — likely because pandas serialized them with a time component
(e.g. `2025-07-23 00:00:00`), which autodetect didn't parse as a pure date.

**Fix:** rather than reload the data, every view was patched to cast at
query time:

```sql
DATE(TIMESTAMP(login_date)) AS login_date
```

`DATE(TIMESTAMP(...))` was chosen over a plain `CAST(... AS DATE)` because
it correctly handles both bare date strings and full datetime strings,
whereas a direct cast only handles the former.

---

### Mistake 8 — Misleading percentage formatting in the dashboard
**What went wrong:** every High-risk client in the table showed a "Login
change (30d)" of exactly **-1%**, which looked like a display bug (or
worse, a logic bug making every high-risk client identical).

**Root cause:** `login_change_30d_pct` is stored as a *fraction*
(e.g. `-0.4` = -40%), with a `-1` sentinel value meaning "no prior-window
logins exist to compare against." Streamlit's `NumberColumn` format
string `"%.0f%%"` appends a `%` sign but does **not** multiply the
underlying value by 100 — so the sentinel `-1` rendered as the literal
text "-1%" instead of "-100%," and all other fractional values displayed
as 0%.

**Fix:** multiply the column into a true percentage before display:

```python
table["login_change_30d_pct"] = table["login_change_30d_pct"] * 100
```

**Worth noting:** once fixed, the -100% pattern for High-risk clients
turned out to be *correct*, not a bug — it reflects the simulation design,
where high-risk clients' login probability decays toward near-zero, so
many genuinely have zero logins in the trailing 30-day window.

---

## 4. Key Takeaways & Lessons Learned

1. **Don't trust a platform's documented policy over what the sign-up
   flow actually shows you.** Snowflake's "no card required" claim didn't
   match the real flow. If a free-tier claim matters to your budget,
   verify it by starting the sign-up, not by reading the docs alone.

2. **Match your commands to your actual shell.** `export` is bash;
   Windows CMD needs `set`. This single mismatch caused two separate
   debugging detours (env vars, and almost a repeat with auth). If
   copying commands from any guide (including this one), check the shell
   syntax matches your terminal.

3. **CLI auth and library auth are often two different credential
   stores.** `gcloud init`/`gcloud auth login` authenticates the CLI tool;
   Python libraries frequently need `gcloud auth application-default
   login` as a separate step. This is a common trap across most cloud
   providers, not just GCP.

4. **`autodetect=True` schema inference is convenient but not
   bulletproof**, especially for dates with inconsistent formatting
   (date-only vs. datetime strings). For a rebuild, either explicitly
   define the schema at load time, or standardize date formatting in
   pandas *before* export to CSV (e.g. `df['col'].dt.strftime('%Y-%m-%d')`)
   to avoid the STRING/DATE mismatch entirely.

5. **Formatting bugs can look like logic bugs.** The -1% display issue
   initially looked like every high-risk client had identical (possibly
   fake-looking) data. Always sanity-check *what a number actually means*
   before assuming the underlying computation is wrong — the fix here was
   in presentation, not in the SQL.

6. **Keep a "sentinel value" clearly separate from real data early.**
   Using `-1` to mean "no data" inside a numeric column that's otherwise a
   genuine percentage is exactly what caused Mistake 8. A rebuild might
   instead use `NULL` end-to-end and handle the "no prior data" case
   explicitly in the UI (e.g. displaying "No activity" as text rather than
   a misleading number).

7. **Separate the "answer key" from the feature set at the data layer,
   not the modelling layer.** Exporting `risk_segment` to its own CSV
   (never loaded into the same table as the features) made it structurally
   impossible to leak it into the score — a good habit to repeat in any
   future project with simulated ground truth.

8. **Working directory and environment variable state are the most common
   "invisible" sources of confusion** when moving between a chat
   assistant and a real terminal. Several of the debugging steps above
   weren't code bugs at all — they were state that didn't carry over
   between terminal sessions. Worth building a habit of always confirming
   `cd` and any `set`/`export` commands at the start of a new session,
   before running anything else.
