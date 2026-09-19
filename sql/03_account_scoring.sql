-- Signal aggregates per account over the policy window. Python turns these into sub-scores.
-- Parameters: $window_days
CREATE OR REPLACE VIEW v_signal_aggregates AS
WITH recent AS (
    SELECT * FROM intent_signals
    WHERE signal_timestamp >= CURRENT_TIMESTAMP - INTERVAL ($window_days) DAY
)
SELECT
    a.account_id,
    COALESCE(SUM(CASE WHEN s.signal_type = 'pricing_page_visit'        THEN s.signal_value END), 0) AS pricing_page_visits,
    COALESCE(SUM(CASE WHEN s.signal_type = 'demo_request'              THEN s.signal_value END), 0) AS demo_requests,
    COALESCE(SUM(CASE WHEN s.signal_type = 'job_posting_ml_engineer'   THEN s.signal_value END), 0) AS ml_job_postings,
    COALESCE(SUM(CASE WHEN s.signal_type = 'funding_event'             THEN s.signal_value END), 0) AS funding_events,
    COALESCE(SUM(CASE WHEN s.signal_type = 'open_source_model_interest' THEN s.signal_value END), 0) AS oss_interest,
    COALESCE(SUM(CASE WHEN s.signal_type = 'website_visit'             THEN s.signal_value END), 0) AS website_visits,
    COALESCE(SUM(CASE WHEN s.signal_type = 'email_engagement'          THEN s.signal_value END), 0) AS email_engagements,
    MAX(s.signal_timestamp) AS last_signal_at
FROM accounts a
LEFT JOIN recent s ON s.account_id = a.account_id
GROUP BY a.account_id;

CREATE OR REPLACE VIEW v_latest_usage AS
SELECT account_id, month, api_calls, active_users, mom_growth_pct
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY month DESC) AS rn
    FROM usage_signals
) t
WHERE rn = 1;
