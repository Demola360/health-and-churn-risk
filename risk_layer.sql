-- ============================================================================
-- Day 3-4: SQL risk layer
-- Client Health & Churn Risk Dashboard
--
-- Builds on the four raw tables loaded by load_to_bigquery.py:
--   client_retention.market_data      (banking sector OHLCV + volatility)
--   client_retention.clients          (client profile + renewal_date)
--   client_retention.login_activity   (one row per login event)
--   client_retention.support_tickets  (one row per support ticket)
--
-- Run this whole script in the BigQuery console (or split it view-by-view
-- if you want to inspect each layer as you build it — recommended for
-- understanding the logic, since that's next week's goal).
--
-- Replace `client_retention` below with your actual dataset name if it
-- differs from the one set in BQ_DATASET.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. Login activity trend
-- Compares login count in the last 7 days vs the 7 days before that
-- (and same for 30-day windows). A shrinking count = declining engagement,
-- one of the clearest early churn signals.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW client_retention.login_trend AS
WITH logins AS (
  SELECT
    client_id,
    DATE(TIMESTAMP(login_date)) AS login_date
  FROM client_retention.login_activity
),
login_counts AS (
  SELECT
    client_id,
    COUNTIF(login_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)) AS logins_last_7d,
    COUNTIF(login_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
            AND login_date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)) AS logins_prior_7d,
    COUNTIF(login_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS logins_last_30d,
    COUNTIF(login_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
            AND login_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS logins_prior_30d
  FROM logins
  GROUP BY client_id
)
SELECT
  client_id,
  logins_last_7d,
  logins_prior_7d,
  logins_last_30d,
  logins_prior_30d,
  -- % change; NULL-safe against divide-by-zero for clients with no prior activity
  SAFE_DIVIDE(logins_last_7d - logins_prior_7d, NULLIF(logins_prior_7d, 0)) AS login_change_7d_pct,
  SAFE_DIVIDE(logins_last_30d - logins_prior_30d, NULLIF(logins_prior_30d, 0)) AS login_change_30d_pct
FROM login_counts;


-- ----------------------------------------------------------------------------
-- 2. Support ticket trend
-- Rising ticket volume, especially unresolved-within-SLA tickets, signals
-- frustration building ahead of a churn decision.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW client_retention.ticket_trend AS
WITH tickets AS (
  SELECT
    client_id,
    DATE(TIMESTAMP(ticket_date)) AS ticket_date,
    ticket_type,
    resolved_within_sla
  FROM client_retention.support_tickets
)
SELECT
  client_id,
  COUNTIF(ticket_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)) AS tickets_last_7d,
  COUNTIF(ticket_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS tickets_last_30d,
  COUNTIF(ticket_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
          AND NOT resolved_within_sla) AS unresolved_last_30d,
  COUNTIF(ticket_type = 'complaint'
          AND ticket_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS complaints_last_30d
FROM tickets
GROUP BY client_id;


-- ----------------------------------------------------------------------------
-- 3. Days to renewal
-- Risk matters more urgently the closer a client is to a renewal decision.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW client_retention.renewal_window AS
SELECT
  client_id,
  tenure_months,
  policy_value_gbp,
  DATE(TIMESTAMP(renewal_date)) AS renewal_date,
  DATE_DIFF(DATE(TIMESTAMP(renewal_date)), CURRENT_DATE(), DAY) AS days_to_renewal
FROM client_retention.clients;


-- ----------------------------------------------------------------------------
-- 4. Market stress signal
-- A single portfolio-level number (not per-client): average 10-day
-- volatility across the 8 banking tickers over the last 30 days. This is
-- macro context, not a per-client signal — it answers "is the sector under
-- stress right now," which can raise baseline risk tolerance thresholds.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW client_retention.market_stress AS
SELECT
  ROUND(AVG(volatility_10d), 5) AS avg_sector_volatility_30d,
  ROUND(AVG(daily_return), 5) AS avg_sector_return_30d
FROM client_retention.market_data
WHERE DATE(TIMESTAMP(trade_date)) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY);


-- ----------------------------------------------------------------------------
-- 5. Final risk view
-- Combines all signals into one row per client with a 0-100 risk score and
-- a risk tier. Weights are a starting point, not tuned — deliberately
-- simple and explainable rather than a black-box model, so it's easy to
-- walk through in an interview. Refine weights once you can compare scores
-- against the known risk_segment answer key.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW client_retention.client_risk_scores AS
SELECT
  r.client_id,
  r.tenure_months,
  r.policy_value_gbp,
  r.days_to_renewal,
  COALESCE(l.login_change_30d_pct, -1) AS login_change_30d_pct,
  COALESCE(t.tickets_last_30d, 0) AS tickets_last_30d,
  COALESCE(t.unresolved_last_30d, 0) AS unresolved_last_30d,

  -- Risk score: 0-100, higher = higher churn risk.
  -- Each component is clamped so no single factor can push the score out
  -- of range on its own.
  LEAST(100, GREATEST(0,
    -- Declining logins: up to 40 points if logins dropped 100%+
    (40 * LEAST(1, GREATEST(0, -1 * COALESCE(l.login_change_30d_pct, 0))))
    -- Ticket volume: up to 30 points, capped at 6+ tickets in 30 days
    + (30 * LEAST(1, COALESCE(t.tickets_last_30d, 0) / 6.0))
    -- Unresolved tickets: up to 15 points, capped at 3+
    + (15 * LEAST(1, COALESCE(t.unresolved_last_30d, 0) / 3.0))
    -- Renewal proximity: up to 15 points as renewal approaches within 60 days
    + (15 * LEAST(1, GREATEST(0, (60 - r.days_to_renewal) / 60.0)))
  )) AS risk_score

FROM client_retention.renewal_window r
LEFT JOIN client_retention.login_trend l USING (client_id)
LEFT JOIN client_retention.ticket_trend t USING (client_id);


-- Add the risk tier as a final pass (kept separate for readability)
CREATE OR REPLACE VIEW client_retention.client_risk_final AS
SELECT
  *,
  CASE
    WHEN risk_score >= 65 THEN 'High'
    WHEN risk_score >= 35 THEN 'Medium'
    ELSE 'Low'
  END AS risk_tier
FROM client_retention.client_risk_scores;


-- ----------------------------------------------------------------------------
-- Quick sanity checks — run these after creating the views above
-- ----------------------------------------------------------------------------
-- Distribution across risk tiers
-- SELECT risk_tier, COUNT(*) AS n_clients, ROUND(AVG(risk_score),1) AS avg_score
-- FROM client_retention.client_risk_final GROUP BY risk_tier ORDER BY avg_score DESC;

-- Cross-check against the simulated answer key (never expose this in the
-- dashboard — it exists only to validate the scoring logic works)
-- SELECT f.risk_tier, k.risk_segment, COUNT(*) AS n
-- FROM client_retention.client_risk_final f
-- JOIN client_retention.clients_risk_segment_answer_key k USING (client_id)
-- GROUP BY 1, 2 ORDER BY 1, 2;
