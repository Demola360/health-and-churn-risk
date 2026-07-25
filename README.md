## Client Health & Churn Risk Dashboard

**A portfolio project that scores 500 simulated financial-services clients for churn risk, combining real live market data with synthetic client behaviour, and surfaces the highest-risk accounts on a Streamlit dashboard.**

**Live demo:** add your Streamlit Community Cloud link here once deployed
**Data sources:** live banking-sector market data via yfinance, synthetic client behaviour data generated for this project

---

**Data honesty note:** the client-level data (logins, support tickets, renewal dates) is synthetic. It was generated with deliberately realistic risk patterns so the model has genuine signal to find, but it is not real client data, and this is stated plainly here and in any write-up or interview discussion of this project. The market data (banking sector tickers) is real, pulled live via yfinance.

---

## The Client Retention Problem

Financial-services firms lose clients gradually, not suddenly. Logins drop off, support tickets pile up unresolved, a renewal date creeps closer without any sign of engagement. Individually, none of these look urgent. Together, they're a pattern that usually ends in a lost client, and by the time someone notices, it's often too late to intervene.

This dashboard scores every client on that combined pattern, login activity, support ticket trends, days to renewal, and broader market stress in the banking sector, and turns it into a single risk tier so a relationship manager knows exactly which accounts need attention this week, not which ones might.

---

## Repo Structure

```text
Client-Health-Churn-Risk-Dashboard/
│
├── app.py                       # Streamlit dashboard, entry point
├── fetch_market_data.py         # Pulls live OHLCV data for 8 banking tickers
├── generate_client_data.py      # Generates simulated client/login/ticket data
├── load_to_bigquery.py          # Loads all CSVs into BigQuery tables
├── requirements.txt
├── README.md
│
└── sql/
    └── client_risk_final.sql    # Rolling risk CTEs and the combined 0-100 risk view
```

---

## How the Model Works

The dashboard asks one question for each client: given everything we can see about their recent behaviour, how much risk do they carry of leaving?

Four signals feed into that score:

1. **Login trend** — a 7-day and 30-day rolling comparison of login frequency. A client logging in less than usual is an early, quiet signal.
2. **Support ticket trend** — rising ticket volume, especially unresolved tickets, often precedes a client giving up on a relationship rather than escalating it.
3. **Days to renewal** — risk isn't flat across a contract. A disengaged client thirty days from renewal is a different problem than the same client eight months out.
4. **Market stress** — a proxy signal built from real banking-sector market data (JPM, BAC, WFC, C, GS, MS, HSBC, BCS), on the basis that sector-wide volatility can influence client sentiment even before it shows up in their individual behaviour.

These four signals combine into a single 0 to 100 risk score, calculated in SQL directly on top of the raw tables, then bucketed into risk tiers so a non-technical relationship manager can act on it without needing to understand the underlying query.

---

## Key Decisions Made

1. **BigQuery Sandbox instead of Snowflake:** Snowflake's free trial required card details to sign up. BigQuery's Sandbox tier needs no card and gives a genuine free tier to build against, which mattered more for a self-funded portfolio project than which warehouse looks more familiar on a CV.

2. **Synthetic client data, real market data:** actual client login and support ticket data isn't publicly available for a project like this, so it had to be generated. The generation was deliberately built with realistic risk patterns baked in, rather than pure randomness, so the model would have real signal to detect rather than fitting to noise. The market data didn't need to be synthetic, yfinance provides genuine live pricing, so using it directly made the market-stress signal more credible than faking that too.

3. **Banking sector as the market proxy:** the eight tickers represent major banking and financial institutions, chosen because sector-wide stress in banking is a reasonable proxy for the kind of macro conditions that might affect a financial-services client base, more relevant than an unrelated index.

4. **SQL for the risk logic, not Python:** the rolling trends and the combined risk score are built as SQL views directly in BigQuery, rather than calculated in a pandas script. This keeps the logic close to the data, means the dashboard just reads a finished view instead of recalculating on every load, and reflects how this kind of scoring would likely be built in an actual data warehouse setup.

---

## What the Dashboard Shows

- **Portfolio-level KPIs**: total clients, clients in each risk tier, total policy value at risk
- **Risk tier distribution**: how many clients fall into Low, Medium, and High risk
- **Risk score against days to renewal**: a scatter view showing whether high-risk clients are clustering near renewal dates, where intervention matters most
- **A sortable client table**: every client with their current risk score and tier
- **Per-client drill-down**: the individual signals behind any one client's score, so a relationship manager can see why a client is flagged, not just that they are

In a test run against the current synthetic dataset, the dashboard surfaced 24 of 500 clients (4.8%) in the High risk tier, representing roughly £58,900 in policy value.

---

## Real-World Limitations

1. **The client data is synthetic.** It was built to carry realistic risk patterns, but it is not drawn from a real book of business, and the model hasn't been validated against actual client outcomes.

2. **No feedback loop yet.** There's currently no mechanism to record whether a flagged client actually churned or stayed, which means the risk tiers can't yet be checked against real results or recalibrated over time.

3. **The market stress signal is a proxy, not a measured causal link.** Banking-sector volatility is used as a reasonable stand-in for macro pressure on clients, but the model doesn't establish that market stress actually drives churn for this specific client base.

4. **BigQuery Sandbox tables expire after 60 days of inactivity.** Fine for active development, but anyone picking this project back up after a long break will need to rerun the pipeline before the dashboard has data to read.

---

## Tech Stack

Python · pandas · yfinance · Google BigQuery (Sandbox) · SQL · Streamlit · GitHub Actions

---

## From Proof of Concept to Production

This project was built as a proof of concept to demonstrate the full pipeline, from live and synthetic data, through a SQL-based scoring layer, to an interactive dashboard. A production version would need a few things this version deliberately leaves out.

It would need real client behavioural data, replacing the synthetic generation step with an actual feed from a CRM or support ticketing system.

It would need a feedback loop, a way for relationship managers to record what actually happened with a flagged client, so the risk model can be checked against real outcomes and recalibrated rather than running on assumptions indefinitely.

It would also need scheduled, automated data refreshes, the market data pipeline is already set up to run on a schedule via GitHub Actions, but a live client feed would need the same treatment so the dashboard reflects current conditions rather than a point-in-time snapshot.
