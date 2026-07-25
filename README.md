# Client Health & Retention Risk Prioritisation Dashboard

*(previously named "Client Health & Churn Risk Dashboard" — renamed to
avoid implying a trained predictive model; see Limitations below)*

**A portfolio project that scores 500 simulated financial-services clients
for retention risk, combining real live banking-sector market data with
synthetic client behaviour, and surfaces the highest-risk accounts on a
Streamlit dashboard.**

**Live dashboard:** https://health-and-churn-risk.streamlit.app
*(update this link if you redeploy under a different URL)*

**Data sources:** live banking-sector market data via `yfinance`; synthetic
client behaviour data generated for this project.

---

## The client retention problem

Financial-services firms lose clients gradually, not suddenly. Logins drop
off, support tickets pile up unresolved, a renewal date creeps closer
without any sign of engagement. Individually, none of these look urgent.
Together, they're a pattern that usually ends in a lost client — and by
the time someone notices, it's often too late to intervene.

This dashboard scores every client on that combined behavioural pattern —
login activity, support ticket trends, and days to renewal — and turns it
into a single risk tier, so a relationship manager knows which accounts
need attention this week, not which ones might.

## What this project is — and isn't

This dashboard **prioritises clients by a rule-based risk score**. It is
**not** a trained churn-prediction model. There is no historical churn
outcome variable, no train/test split, and no precision/recall/ROC-AUC —
because there is no real churn label to learn from or validate against.
See **Limitations** below for the full picture, including what a genuine
predictive version of this project would require.

## Business context (assumed)

This project models a **financial-services provider with an
insurance-style product** — clients hold a policy with a renewal date and
a policy value, and engage via a client portal (logins) and a support desk
(tickets). The specific type of institution (insurer, wealth platform,
broker) isn't pinned down further; this is a deliberate simplification for
a portfolio project, not a real organisation's actual retention program. A
production version would start with a stakeholder-validated business
problem statement and a precise definition of "churn" (e.g. "policy not
renewed within 30 days of its renewal date") before any modelling work.

## Data honesty note

The client-level data (logins, support tickets, renewal dates) is
**synthetic**. It was generated with deliberately realistic risk patterns
so the scoring logic has genuine signal to find, but it is not real client
data — stated plainly here, in the dashboard footer, and in any write-up
or interview discussion of this project. The banking-sector market data is
real, pulled live via `yfinance`.

---

## How the model works

The dashboard asks one question for each client: given everything
observable about their recent behaviour, how much risk do they carry of
not renewing?

Three signals feed into the score, each capped so no single factor can
dominate:

| Signal | Max points | What it measures |
|---|---|---|
| Login trend | 40 | A 7-day and 30-day rolling comparison of login frequency. A client who's gone silent, or whose logins have genuinely declined, is an early, quiet signal. |
| Support ticket trend | 30 (+15 unresolved) | Rising ticket volume — especially unresolved tickets — often precedes a client giving up rather than escalating. |
| Renewal proximity | 15 | Risk isn't flat across a contract. A disengaged client 30 days from renewal is a different problem than the same client 8 months out. |

These combine into a single 0–100 risk score, calculated in SQL directly
on top of the raw tables, then bucketed into Low/Medium/High tiers so a
non-technical relationship manager can act on it without reading the
underlying query.

**Market stress is shown, not scored.** A fourth view (`market_stress`)
summarises volatility across 8 banking-sector tickers (JPM, BAC, WFC, C,
GS, MS, HSBC, BCS) as portfolio-level context in the dashboard. It is
**not** joined to individual clients or added to the risk score — there's
no evidence in this project that sector-wide volatility predicts
individual client churn, so that claim isn't made. See Limitations for
what it would take to justify including it properly.

## Key decisions made

1. **BigQuery Sandbox instead of Snowflake.** Snowflake's free trial
   required card details to sign up despite documentation suggesting
   otherwise. BigQuery's Sandbox tier needs no card and gives a genuine
   free tier to build against — which mattered more for a self-funded
   portfolio project than which warehouse looks more familiar on a CV.

2. **Synthetic client data, real market data.** Real client login and
   support ticket data isn't publicly available for a project like this,
   so it had to be generated. The generator deliberately builds in
   realistic risk patterns rather than pure randomness, so the scoring
   logic has real signal to detect rather than fitting to noise. The
   market data didn't need to be synthetic — `yfinance` provides genuine
   live pricing — so using it directly made that signal more credible than
   faking it too.

3. **Banking sector as the market-context proxy.** The eight tickers
   represent major banking and financial institutions, chosen because
   sector-wide stress in banking is a reasonable proxy for the kind of
   macro conditions that might affect a financial-services client base —
   more relevant than an unrelated index, even though (see above) it isn't
   currently wired into the score itself.

4. **SQL for the risk logic, not Python.** The rolling trends and the
   combined risk score are built as SQL views directly in BigQuery, rather
   than calculated in a pandas script. This keeps the logic close to the
   data, means the dashboard just reads a finished view instead of
   recalculating on every load, and reflects how this kind of scoring
   would likely be built in an actual data warehouse setup.

## What the dashboard shows

- **Portfolio-level KPIs** — total clients, clients in each risk tier,
  total policy value at risk
- **Risk tier distribution** — how many clients fall into Low, Medium, and
  High risk, colour-coded
- **Risk score vs. days to renewal** — a scatter view (bubble size =
  policy value) showing whether high-risk clients cluster near renewal
  dates, where intervention matters most
- **A sortable, filterable client table** — every client with their
  current risk score, tier, and renewal status (Upcoming / Renewal due
  soon / Lapsed)
- **Per-client drill-down** — the individual signals behind any one
  client's score, so a relationship manager can see *why* a client is
  flagged, not just that they are

In a test run against the current synthetic dataset, the dashboard
surfaced 24 of 500 clients (4.8%) in the High risk tier, representing
roughly £58,900 in policy value.

---

## Tech stack

- **Python/pandas** — data generation and transformation
- **yfinance** — live banking-sector market data
- **Google BigQuery (Sandbox)** — data warehouse, free, no credit card
- **BigQuery SQL** — rolling-window risk signals, combined into a
  transparent 0–100 weighted score
- **Streamlit / Plotly** — interactive dashboard, deployed on Streamlit
  Community Cloud
- **GitHub Actions** — *planned, not yet implemented* (see Limitations)

## Repo structure

```text
health-and-churn-risk/
│
├── app.py                       # Streamlit dashboard, entry point
├── fetch_market_data.py         # Pulls live OHLCV data for 8 banking tickers
├── generate_client_data.py      # Generates simulated client/login/ticket data
├── load_to_bigquery.py          # Loads the 4 core CSVs into BigQuery
├── load_answer_key.py           # Loads the synthetic answer key, validation-only
├── risk_layer.sql               # Rolling risk CTEs and the combined 0-100 risk view
├── secrets.toml.example         # Template for Streamlit Cloud deployment credentials
├── requirements.txt
└── README.md
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```
For a fully reproducible environment matching what was tested, generate a
lockfile after your first successful run: `pip freeze > requirements-lock.txt`

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
python load_to_bigquery.py        # creates the dataset (if needed) and loads the 4 core CSVs
python load_answer_key.py         # optional — loads the synthetic answer key for the sanity-check query only
```

### 4. Build the SQL layer
Run `risk_layer.sql` in the BigQuery console (paste the whole file, run
once). This creates six views: `login_trend`, `ticket_trend`,
`renewal_window`, `market_stress`, `client_risk_scores`, and
`client_risk_final`.

### 5. Run the dashboard
```bash
streamlit run app.py
```

### Verify
```sql
SELECT COUNT(*) FROM `client_retention.market_data`;
SELECT COUNT(*) FROM `client_retention.clients`;
SELECT COUNT(*) FROM `client_retention.login_activity`;
SELECT COUNT(*) FROM `client_retention.support_tickets`;
```

**Note:** Sandbox tables auto-expire after 60 days by default — fine while
actively building, just re-run the pipeline if picking this back up after
a long break.

## Deploying to Streamlit Community Cloud
See `secrets.toml.example` for the required secrets format (BigQuery
service account credentials, since the cloud environment has no local
`gcloud` login). Push to a GitHub repo, connect it at
[share.streamlit.io](https://share.streamlit.io), and paste the filled-in
secrets into the app's Settings → Secrets before deploying.

---

## Limitations (read this before quoting numbers from this project)

This section exists because a portfolio project claiming more than it
delivers is worse than one that's upfront about its scope. If reviewing
this as a hiring manager or interviewer, this is the honest account of
what's built vs. what's aspirational.

- **Not a trained model.** The risk score is a hand-weighted rule set
  (40/30/15/15), chosen for transparency and explainability, not fitted or
  validated against real outcomes. A genuine predictive version would need
  a defined churn outcome (e.g. `churned_within_60_days`), a train/test
  split, and standard classification metrics (precision, recall, ROC-AUC)
  — ideally reported as "precision among the top N highest-risk clients an
  intervention team can actually contact" rather than raw accuracy.
- **No feedback loop.** There's no mechanism to record whether a flagged
  client actually churned or stayed, so the risk tiers can't yet be
  checked against real outcomes or recalibrated over time.
- **The synthetic answer key does not validate the model.** The optional
  sanity check (bottom of `risk_layer.sql`, requires `load_answer_key.py`)
  compares the risk score against the hidden `risk_segment` used to
  *generate* the synthetic data. A match only shows the scoring rules can
  rediscover patterns that were deliberately built in — a pipeline smoke
  test, not evidence the approach would work on real client data.
- **Market data is contextual, not predictive, in the current build.**
  The banking-sector volatility signal is displayed but not joined to
  client-level risk. Doing so honestly would require evidence that
  sector-wide market stress actually correlates with individual client
  churn in this business context — that evidence doesn't exist here, so
  the claim isn't made.
- **No formal business-analysis artefacts.** There's no stakeholder map,
  requirements document, or acceptance-criteria set backing this project —
  appropriate for a solo technical portfolio piece, but a real BA
  engagement would produce these before any dashboard work started.
- **No automated tests.** No unit tests, schema tests, or data-quality
  assertions exist yet. For a project this size, the practical middle
  ground is a lightweight validation script rather than a full test suite.
- **BigQuery Sandbox tables expire after 60 days of inactivity.** Fine for
  active development, but anyone picking this project back up after a long
  break needs to rerun the pipeline before the dashboard has data to read.

## From proof of concept to production

This project was built to demonstrate a full pipeline — from live and
synthetic data, through a SQL-based scoring layer, to an interactive
dashboard. A production version would need several things this version
deliberately leaves out:

- **Real client behavioural data**, replacing the synthetic generation
  step with an actual feed from a CRM or support ticketing system.
- **A feedback loop**, so relationship managers can record what actually
  happened with a flagged client, letting the risk model be checked
  against real outcomes and recalibrated rather than running on
  assumptions indefinitely.
- **Scheduled, automated data refreshes.** GitHub Actions is listed in the
  tech stack as the intended mechanism for running `fetch_market_data.py`
  on a schedule, but the workflow file doesn't exist yet — this is planned
  future work, not a currently running feature. A live client feed would
  need the same treatment so the dashboard reflects current conditions
  rather than a point-in-time snapshot.
- **A trained, validated churn model**, per the Limitations above, with a
  real outcome variable and out-of-sample evaluation.

## Files
| File | Purpose |
|---|---|
| `fetch_market_data.py` | Pulls live OHLCV data for 8 banking tickers |
| `generate_client_data.py` | Generates simulated client/login/ticket data |
| `load_to_bigquery.py` | Loads the 4 core CSVs into BigQuery tables |
| `load_answer_key.py` | Loads the synthetic answer key separately, for validation only |
| `risk_layer.sql` | SQL views: rolling trends, renewal window, market stress, combined risk score |
| `app.py` | Streamlit dashboard |
| `requirements.txt` | Python dependencies |
| `requirements-lock.txt` | Exact pinned versions confirmed working (generate with `pip freeze > requirements-lock.txt`) |
| `secrets.toml.example` | Template for Streamlit Cloud deployment credentials |
