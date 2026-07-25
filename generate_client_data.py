"""
Day 1 - Step 2: Simulated client data
Generates synthetic client records: login activity, support tickets, and
renewal dates. This is clearly labelled as SIMULATED data throughout the
project (README, dashboard footer, interview talking points) — no claim is
ever made that this is real client data. That's the honest framing for a
portfolio piece built on a domain (insurance/financial services client
retention) where real data isn't available.

Design intent: bake in a few realistic risk patterns (declining logins,
rising support tickets, near-term renewal) so the eventual churn model has
genuine signal to find — not pure noise.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)  # reproducible synthetic data

N_CLIENTS = 500
SIM_DAYS = 365
START_DATE = datetime.today() - timedelta(days=SIM_DAYS)


def generate_clients(n_clients=N_CLIENTS) -> pd.DataFrame:
    """One row per client: profile + an assigned latent 'risk_segment' that
    drives how their behaviour is simulated below."""
    client_ids = [f"CLI{str(i).zfill(5)}" for i in range(1, n_clients + 1)]

    # Latent risk segment — not shown to the model, used only to generate
    # believable behaviour patterns. 20% high risk, 30% medium, 50% low.
    risk_segment = np.random.choice(
        ["high", "medium", "low"], size=n_clients, p=[0.2, 0.3, 0.5]
    )

    tenure_months = np.random.randint(3, 84, size=n_clients)
    policy_value = np.round(np.random.gamma(shape=3, scale=800, size=n_clients), 2)

    renewal_date = [
        START_DATE + timedelta(days=int(np.random.randint(30, SIM_DAYS + 90)))
        for _ in range(n_clients)
    ]

    return pd.DataFrame({
        "client_id": client_ids,
        "tenure_months": tenure_months,
        "policy_value_gbp": policy_value,
        "renewal_date": renewal_date,
        "risk_segment": risk_segment,  # kept for validation only, drop before modelling
    })


def generate_login_activity(clients: pd.DataFrame) -> pd.DataFrame:
    """Daily login flag per client, with high-risk clients showing a declining
    trend over the simulation window (a classic disengagement signal)."""
    rows = []
    dates = [START_DATE + timedelta(days=d) for d in range(SIM_DAYS)]

    base_prob = {"high": 0.35, "medium": 0.55, "low": 0.7}

    for _, client in clients.iterrows():
        p0 = base_prob[client["risk_segment"]]
        for day_idx, date in enumerate(dates):
            # High-risk clients decay toward near-zero login probability;
            # others stay roughly flat with small noise.
            if client["risk_segment"] == "high":
                decay = max(0.02, p0 * (1 - day_idx / SIM_DAYS))
            else:
                decay = p0
            logged_in = np.random.rand() < decay
            if logged_in:
                rows.append({"client_id": client["client_id"], "login_date": date})

    return pd.DataFrame(rows)


def generate_support_tickets(clients: pd.DataFrame) -> pd.DataFrame:
    """Support ticket events, with high-risk clients raising more tickets,
    especially in the back half of the window (frustration building up)."""
    rows = []
    ticket_types = ["billing", "claim_query", "policy_change", "complaint", "general"]

    for _, client in clients.iterrows():
        if client["risk_segment"] == "high":
            n_tickets = np.random.poisson(6)
        elif client["risk_segment"] == "medium":
            n_tickets = np.random.poisson(2)
        else:
            n_tickets = np.random.poisson(0.5)

        for _ in range(n_tickets):
            # Weight ticket timing toward the second half of the window for
            # high-risk clients — tickets cluster before churn/non-renewal.
            if client["risk_segment"] == "high":
                day_offset = int(np.random.triangular(SIM_DAYS * 0.4, SIM_DAYS, SIM_DAYS))
            else:
                day_offset = int(np.random.uniform(0, SIM_DAYS))

            rows.append({
                "client_id": client["client_id"],
                "ticket_date": START_DATE + timedelta(days=min(day_offset, SIM_DAYS - 1)),
                "ticket_type": np.random.choice(ticket_types),
                "resolved_within_sla": np.random.rand() > (
                    0.3 if client["risk_segment"] == "high" else 0.1
                ),
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    clients = generate_clients()
    logins = generate_login_activity(clients)
    tickets = generate_support_tickets(clients)

    # risk_segment is the "answer key" used only to sanity-check the model
    # later — export it separately so it's never accidentally used as a
    # model feature.
    clients.drop(columns=["risk_segment"]).to_csv("clients.csv", index=False)
    clients[["client_id", "risk_segment"]].to_csv("clients_risk_segment_ANSWER_KEY.csv", index=False)
    logins.to_csv("login_activity.csv", index=False)
    tickets.to_csv("support_tickets.csv", index=False)

    print(f"Clients:        {len(clients)} rows -> clients.csv")
    print(f"Login events:   {len(logins)} rows -> login_activity.csv")
    print(f"Support tickets:{len(tickets)} rows -> support_tickets.csv")
    print("Risk segment answer key saved separately (do not use as a model feature).")
