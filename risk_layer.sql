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
--
-- IMPORTANT: percentage change alone is ambiguous when either window has
-- zero logins (0 -> 5 looks identical to "no data" using SAFE_DIVIDE alone,
-- and 5 -> 0 vs 0 -> 0 both stringify as -100%/NULL if not handled
-- explicitly). login_activity_status disambiguates these cases so scoring
-- and display can't disagree with each other.
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
  -- Left as a genuine NULL (not a sentinel) when prior activity is zero —
  -- a percentage change from zero is mathematically undefined, not -100%.
  SAFE_DIVIDE(logins_last_7d - logins_prior_7d, NULLIF(logins_prior_7d, 0)) AS login_change_7d_pct,
  SAFE_DIVIDE(logins_last_30d - logins_prior_30d, NULLIF(logins_prior_30d, 0)) AS login_change_30d_pct,
  CASE
    WHEN logins_last_30d = 0 AND logins_prior_30d = 0 THEN 'no_activity_either_window'
    WHEN logins_prior_30d = 0 AND logins_last_30d > 0 THEN 'new_or_reactivated'
    WHEN logins_last_30d = 0 AND logins_prior_30d > 0 THEN 'went_silent'
    WHEN logins_last_30d < logins_prior_30d THEN 'declined'
    WHEN logins_last_30d > logins_prior_30d THEN 'increased'
    ELSE 'flat'
  END AS login_activity_status
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
-- against the known risk_segment answer key (see the sanity-check query at
-- the bottom of this file — note that comparison only checks whether this
-- rule-based score can rediscover patterns that were deliberately built
-- into the synthetic data; it is NOT a substitute for validating against
-- real churn outcomes).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW client_retention.client_risk_scores AS
WITH scored AS (
  SELECT
    r.client_id,
    r.tenure_months,
    r.policy_value_gbp,
    r.days_to_renewal,
    CASE
      WHEN r.days_to_renewal < 0 THEN 'Lapsed'
      WHEN r.days_to_renewal <= 30 THEN 'Renewal due soon'
      ELSE 'Upcoming'
    END AS renewal_status,
    -- Genuine NULL when there's no prior-window activity to compare against —
    -- displayed as-is rather than forced into a misleading -100%.
    l.login_change_30d_pct,
    COALESCE(l.login_activity_status, 'no_login_records_at_all') AS login_activity_status,
    COALESCE(t.tickets_last_30d, 0) AS tickets_last_30d,
    COALESCE(t.unresolved_last_30d, 0) AS unresolved_last_30d,

    -- Each component exposed individually (not just summed) so the
    -- dashboard can say exactly which signal drove a client's score,
    -- instead of guessing from the raw inputs after the fact.
    (CASE
       WHEN l.client_id IS NULL THEN 40
       WHEN l.login_activity_status IN ('went_silent', 'no_activity_either_window') THEN 40
       WHEN l.login_activity_status = 'declined'
         THEN 40 * LEAST(1, GREATEST(0, -1 * l.login_change_30d_pct))
       ELSE 0
     END) AS login_risk_points,

    -- Ticket volume + unresolved combined into one "ticket-related" bucket
    -- (max 45) so the driver breakdown stays a clean 3-way split against
    -- login (max 40) and renewal (max 15).
    (30 * LEAST(1, COALESCE(t.tickets_last_30d, 0) / 6.0))
      + (15 * LEAST(1, COALESCE(t.unresolved_last_30d, 0) / 3.0)) AS ticket_risk_points,

    (15 * LEAST(1, GREATEST(0, (60 - r.days_to_renewal) / 60.0))) AS renewal_risk_points

  FROM client_retention.renewal_window r
  LEFT JOIN client_retention.login_trend l USING (client_id)
  LEFT JOIN client_retention.ticket_trend t USING (client_id)
)
SELECT
  *,
  LEAST(100, GREATEST(0, login_risk_points + ticket_risk_points + renewal_risk_points)) AS risk_score
FROM scored;


-- Add the risk tier and a recommended action as a final pass (kept
-- separate for readability). The action logic is intentionally simple —
-- tier + renewal urgency only — matching the transparency of the scoring
-- rules themselves rather than adding hidden complexity at the last step.
CREATE OR REPLACE VIEW client_retention.client_risk_final AS
SELECT
  *,
  CASE
    WHEN risk_score >= 65 THEN 'High'
    WHEN risk_score >= 35 THEN 'Medium'
    ELSE 'Low'
  END AS risk_tier,
  CASE
    WHEN risk_score >= 65 AND renewal_status = 'Lapsed'
      THEN 'Recovery call — policy already lapsed, contact immediately'
    WHEN risk_score >= 65 AND renewal_status = 'Renewal due soon'
      THEN 'Priority retention outreach before renewal date'
    WHEN risk_score >= 65
      THEN 'Proactive check-in — high risk, renewal not yet imminent'
    WHEN risk_score >= 35 AND renewal_status IN ('Lapsed', 'Renewal due soon')
      THEN 'Soft touchpoint ahead of renewal decision'
    WHEN risk_score >= 35
      THEN 'Monitor — flag if score rises further'
    ELSE 'No action needed'
  END AS recommended_action
FROM client_retention.client_risk_scores;


-- ----------------------------------------------------------------------------
-- Quick sanity checks — run these after creating the views above
-- ----------------------------------------------------------------------------
-- Distribution across risk tiers
-- SELECT risk_tier, COUNT(*) AS n_clients, ROUND(AVG(risk_score),1) AS avg_score
-- FROM client_retention.client_risk_final GROUP BY risk_tier ORDER BY avg_score DESC;

-- Cross-check against the simulated answer key. IMPORTANT: this only tests
-- whether the rule-based score can rediscover patterns that were
-- deliberately built into the synthetic data generator — it is a pipeline
-- sanity check, not model validation against real churn outcomes. Requires
-- running load_answer_key.py first, which loads this table separately from
-- the four tables used everywhere else (never joined into client_risk_final).
-- SELECT f.risk_tier, k.risk_segment, COUNT(*) AS n
-- FROM client_retention.client_risk_final f
-- JOIN client_retention.clients_risk_segment_answer_key k USING (client_id)
-- GROUP BY 1, 2 ORDER BY 1, 2;
