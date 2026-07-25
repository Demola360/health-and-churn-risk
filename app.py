"""
Day 5: Streamlit dashboard
Client Health & Churn Risk Dashboard

Reads directly from the client_retention.client_risk_final view in BigQuery
(built in risk_layer.sql) and presents portfolio-level risk metrics plus
client-level drill-down.

Run with:
    streamlit run app.py

Requires the same environment variables and auth as load_to_bigquery.py:
    set GCP_PROJECT_ID=health-and-churn-risk
    set BQ_DATASET=client_retention
"""

import os
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

st.set_page_config(
    page_title="Client Health & Churn Risk Dashboard",
    page_icon="\U0001F4CA",
    layout="wide",
)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID") or st.secrets.get("GCP_PROJECT_ID", "health-and-churn-risk")
DATASET = os.environ.get("BQ_DATASET") or st.secrets.get("BQ_DATASET", "client_retention")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_resource
def get_client() -> bigquery.Client:
    # On Streamlit Community Cloud there's no local gcloud login, so a
    # service account key stored in st.secrets is used instead. Locally,
    # neither secret is set, so this falls back to your `gcloud auth
    # application-default login` credentials exactly as before.
    if "gcp_service_account" in st.secrets:
        credentials = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"])
        )
        return bigquery.Client(project=PROJECT_ID, credentials=credentials)
    return bigquery.Client(project=PROJECT_ID)


@st.cache_data(ttl=600)
def load_risk_data() -> pd.DataFrame:
    client = get_client()
    query = f"""
        SELECT *
        FROM `{PROJECT_ID}.{DATASET}.client_risk_final`
    """
    return client.query(query).to_dataframe()


@st.cache_data(ttl=600)
def load_market_stress() -> pd.DataFrame:
    client = get_client()
    query = f"""
        SELECT *
        FROM `{PROJECT_ID}.{DATASET}.market_stress`
    """
    return client.query(query).to_dataframe()


# ---------------------------------------------------------------------------
# Load data (with a clear error if BigQuery isn't reachable)
# ---------------------------------------------------------------------------
try:
    df = load_risk_data()
    market = load_market_stress()
except Exception as e:
    st.error(
        "Couldn't load data from BigQuery. Check that GCP_PROJECT_ID and "
        "BQ_DATASET are set correctly and that you're authenticated "
        "(gcloud auth application-default login)."
    )
    st.exception(e)
    st.stop()

TIER_ORDER = ["High", "Medium", "Low"]
TIER_COLOR = {"High": "#d62728", "Medium": "#ff7f0e", "Low": "#2ca02c"}


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Client Health & Churn Risk Dashboard")
st.caption(
    "Client behavioural data (logins, support tickets, renewal dates) is "
    "**simulated** with deliberately realistic risk patterns. Banking-sector "
    "market data is live, pulled via yfinance."
)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")
selected_tiers = st.sidebar.multiselect(
    "Risk tier", options=TIER_ORDER, default=TIER_ORDER
)
max_days = int(df["days_to_renewal"].max()) if not df.empty else 365
renewal_window = st.sidebar.slider(
    "Days to renewal (max)", min_value=0, max_value=max(max_days, 1), value=max(max_days, 1)
)

filtered = df[
    df["risk_tier"].isin(selected_tiers) & (df["days_to_renewal"] <= renewal_window)
]

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

total_clients = len(filtered)
high_risk_n = int((filtered["risk_tier"] == "High").sum())
high_risk_pct = (high_risk_n / total_clients * 100) if total_clients else 0
avg_score = filtered["risk_score"].mean() if total_clients else 0
value_at_risk = filtered.loc[filtered["risk_tier"] == "High", "policy_value_gbp"].sum()

col1.metric("Clients (filtered)", f"{total_clients:,}")
col2.metric("High risk", f"{high_risk_n:,}", f"{high_risk_pct:.1f}% of total")
col3.metric("Avg risk score", f"{avg_score:.1f} / 100")
col4.metric("Policy value at risk (High tier)", f"\u00a3{value_at_risk:,.0f}")

if not market.empty:
    st.caption(
        f"Banking sector context (last 30d): avg volatility "
        f"{market['avg_sector_volatility_30d'].iloc[0]:.4f}, "
        f"avg daily return {market['avg_sector_return_30d'].iloc[0]:.4f}"
    )

st.divider()

# ---------------------------------------------------------------------------
# Risk tier distribution + scatter
# ---------------------------------------------------------------------------
left, right = st.columns([1, 2])

with left:
    st.subheader("Risk tier distribution")
    st.caption("How many clients fall into each risk category, right now.")

    tier_counts = (
        filtered["risk_tier"].value_counts().reindex(TIER_ORDER).fillna(0).astype(int)
    )
    tier_df = pd.DataFrame({"risk_tier": tier_counts.index, "n_clients": tier_counts.values})

    fig_bar = px.bar(
        tier_df,
        x="risk_tier",
        y="n_clients",
        color="risk_tier",
        color_discrete_map=TIER_COLOR,
        category_orders={"risk_tier": TIER_ORDER},
        text="n_clients",
        labels={"risk_tier": "Risk tier", "n_clients": "Number of clients"},
    )
    fig_bar.update_traces(textposition="outside")
    fig_bar.update_layout(showlegend=False, yaxis_title="Clients", xaxis_title=None)
    st.plotly_chart(fig_bar, use_container_width=True)

with right:
    st.subheader("Risk score vs. days to renewal")
    st.caption(
        "Each dot is a client. Further left = renewal is closer. Higher up = "
        "riskier. Bigger dot = higher policy value. The clients worth acting "
        "on first sit in the top-left with a large bubble."
    )

    fig_scatter = px.scatter(
        filtered,
        x="days_to_renewal",
        y="risk_score",
        color="risk_tier",
        size="policy_value_gbp",
        color_discrete_map=TIER_COLOR,
        category_orders={"risk_tier": TIER_ORDER},
        hover_name="client_id",
        hover_data={
            "risk_tier": True,
            "policy_value_gbp": ":.0f",
            "days_to_renewal": True,
            "risk_score": True,
        },
        labels={
            "days_to_renewal": "Days to renewal (negative = already passed)",
            "risk_score": "Risk score",
            "risk_tier": "Risk tier",
        },
    )
    fig_scatter.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig_scatter.update_layout(legend_title_text="Risk tier")
    st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Client table
# ---------------------------------------------------------------------------
st.subheader("Client detail")

sort_by = st.selectbox(
    "Sort by", options=["risk_score", "days_to_renewal", "policy_value_gbp"], index=0
)
ascending = st.checkbox("Ascending", value=False)

display_cols = [
    "client_id", "risk_tier", "risk_score", "days_to_renewal",
    "tenure_months", "policy_value_gbp", "login_change_30d_pct",
    "tickets_last_30d", "unresolved_last_30d",
]
table = filtered[display_cols].sort_values(sort_by, ascending=ascending).copy()

# login_change_30d_pct is stored as a fraction (e.g. -0.4 = -40%); the
# sentinel value -1 means "no prior-window logins to compare against" —
# multiply into a true percentage so the table reads correctly either way.
table["login_change_30d_pct"] = table["login_change_30d_pct"] * 100

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "risk_score": st.column_config.ProgressColumn(
            "Risk score", min_value=0, max_value=100, format="%.0f"
        ),
        "policy_value_gbp": st.column_config.NumberColumn(
            "Policy value", format="\u00a3%.0f"
        ),
        "login_change_30d_pct": st.column_config.NumberColumn(
            "Login change (30d)", format="%.0f%%",
            help="-100% means no logins at all in the last 30 days versus the prior 30",
        ),
    },
)

st.divider()

# ---------------------------------------------------------------------------
# Client drill-down
# ---------------------------------------------------------------------------
st.subheader("Drill down into a client")
client_options = filtered["client_id"].tolist()
if client_options:
    selected_client = st.selectbox("Client ID", options=client_options)
    row = filtered[filtered["client_id"] == selected_client].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Risk score", f"{row['risk_score']:.0f} / 100", row["risk_tier"])
    c2.metric("Days to renewal", f"{row['days_to_renewal']:.0f}")
    c3.metric("Policy value", f"\u00a3{row['policy_value_gbp']:,.0f}")

    c4, c5, c6 = st.columns(3)
    c4.metric("Login change (30d)", f"{row['login_change_30d_pct']*100:.0f}%")
    c5.metric("Tickets (30d)", f"{row['tickets_last_30d']:.0f}")
    c6.metric("Unresolved tickets (30d)", f"{row['unresolved_last_30d']:.0f}")
else:
    st.info("No clients match the current filters.")

st.caption(
    "Risk score is a transparent weighted rule (declining logins, ticket "
    "volume, unresolved tickets, renewal proximity) — not a trained model. "
    "That's a deliberate starting point for interpretability."
)
