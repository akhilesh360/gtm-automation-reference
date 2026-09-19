-- v2: weighted pipeline forecast. Stage probabilities come from config/policy.yaml as parameters.
-- Parameters: $p_prospecting $p_discovery $p_proposal $p_negotiation
CREATE OR REPLACE VIEW v_stage_probability AS
SELECT * FROM (VALUES ('Prospecting', $p_prospecting), ('Discovery', $p_discovery), ('Proposal', $p_proposal),
                      ('Negotiation', $p_negotiation), ('Closed Won', 1.0), ('Closed Lost', 0.0)) AS t(stage, probability);

CREATE OR REPLACE VIEW v_weighted_pipeline AS
SELECT DATE_TRUNC('month', o.close_date)::DATE AS close_month,
       o.source_tier AS account_tier,
       COUNT(*) AS open_opportunities,
       COALESCE(SUM(o.amount), 0) AS open_pipeline,
       COALESCE(SUM(o.amount * p.probability), 0) AS weighted_forecast
FROM opportunities o JOIN v_stage_probability p ON p.stage = o.stage
WHERE NOT o.is_closed
GROUP BY 1, 2 ORDER BY 1, 2;

CREATE OR REPLACE VIEW v_closed_won_by_month AS
SELECT DATE_TRUNC('month', close_date)::DATE AS close_month, source_tier AS account_tier,
       COUNT(*) AS won_opportunities, COALESCE(SUM(amount), 0) AS closed_won_actual
FROM opportunities WHERE is_won GROUP BY 1, 2 ORDER BY 1, 2;

-- forecast vs actual: the latest snapshot taken BEFORE each closed month, compared to what actually closed
CREATE OR REPLACE VIEW v_forecast_vs_actual AS
WITH latest_prior AS (
    SELECT s.close_month, s.account_tier, s.weighted_forecast, s.open_pipeline, s.snapshot_date,
           ROW_NUMBER() OVER (PARTITION BY s.close_month, s.account_tier ORDER BY s.snapshot_date DESC) AS rn
    FROM forecast_snapshots s
    WHERE s.snapshot_date < s.close_month + INTERVAL 1 MONTH
)
SELECT a.close_month, a.account_tier, a.closed_won_actual,
       COALESCE(lp.weighted_forecast, 0) AS weighted_forecast,
       COALESCE(lp.open_pipeline, 0) AS open_pipeline_at_snapshot,
       lp.snapshot_date,
       ROUND(100.0 * a.closed_won_actual / NULLIF(lp.weighted_forecast, 0), 1) AS attainment_pct
FROM v_closed_won_by_month a
LEFT JOIN latest_prior lp ON lp.close_month = a.close_month AND lp.account_tier = a.account_tier AND lp.rn = 1
ORDER BY a.close_month, a.account_tier;

CREATE OR REPLACE VIEW v_forecast_summary AS
SELECT
    COALESCE(SUM(open_pipeline), 0) AS open_pipeline,
    COALESCE(SUM(weighted_forecast), 0) AS weighted_forecast,
    ROUND(100.0 * COALESCE(SUM(weighted_forecast), 0) / NULLIF(SUM(open_pipeline), 0), 1) AS weighted_pct,
    (SELECT COALESCE(SUM(closed_won_actual), 0) FROM v_closed_won_by_month
      WHERE close_month >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL 3 MONTH) AS closed_won_last_3_months
FROM v_weighted_pipeline;
