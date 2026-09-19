-- v2: pipeline funnel, bottleneck and conversion by tier. Snowflake-compatible.
CREATE OR REPLACE VIEW v_stage_order AS
SELECT * FROM (VALUES ('Prospecting', 1), ('Discovery', 2), ('Proposal', 3), ('Negotiation', 4), ('Closed Won', 5)) AS t(stage, stage_order);

-- an opportunity "reached" a stage if it was created there (Prospecting) or ever moved into it
CREATE OR REPLACE VIEW v_stage_reached AS
SELECT o.opportunity_id, o.source_tier, 'Prospecting' AS stage FROM opportunities o
UNION
SELECT h.opportunity_id, o.source_tier, h.to_stage FROM opportunity_stage_history h JOIN opportunities o ON o.opportunity_id = h.opportunity_id
WHERE h.to_stage <> 'Closed Lost';

CREATE OR REPLACE VIEW v_funnel AS
WITH reached AS (
    SELECT s.stage, s.stage_order, COUNT(DISTINCT r.opportunity_id) AS opportunities
    FROM v_stage_order s LEFT JOIN v_stage_reached r ON r.stage = s.stage
    GROUP BY s.stage, s.stage_order
),
steps AS (
    SELECT stage, stage_order, opportunities,
           LAG(opportunities) OVER (ORDER BY stage_order) AS prev_opportunities
    FROM reached
)
SELECT stage, stage_order, opportunities,
       ROUND(100.0 * opportunities / NULLIF(prev_opportunities, 0), 1) AS step_conversion_pct,
       prev_opportunities - opportunities AS dropped,
       ROUND(100.0 * opportunities / NULLIF(FIRST_VALUE(opportunities) OVER (ORDER BY stage_order), 0), 1) AS cumulative_pct
FROM steps ORDER BY stage_order;

CREATE OR REPLACE VIEW v_stage_cycle AS
SELECT from_stage AS stage, s.stage_order,
       COUNT(*) AS transitions,
       ROUND(MEDIAN(days_in_from_stage), 1) AS median_days,
       ROUND(AVG(days_in_from_stage), 1) AS avg_days,
       SUM(CASE WHEN to_stage = 'Closed Lost' THEN 1 ELSE 0 END) AS lost_from_here
FROM opportunity_stage_history h JOIN v_stage_order s ON s.stage = h.from_stage
GROUP BY from_stage, s.stage_order ORDER BY s.stage_order;

-- the bottleneck is the step with the lowest conversion into the next stage
CREATE OR REPLACE VIEW v_bottleneck AS
SELECT f.stage AS to_stage, p.stage AS from_stage, f.step_conversion_pct, f.dropped,
       f.step_conversion_pct = (SELECT MIN(step_conversion_pct) FROM v_funnel WHERE step_conversion_pct IS NOT NULL) AS bottleneck
FROM v_funnel f JOIN v_funnel p ON p.stage_order = f.stage_order - 1
ORDER BY f.stage_order;

CREATE OR REPLACE VIEW v_conversion_by_tier AS
SELECT source_tier,
       COUNT(*) AS opportunities,
       SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) AS closed,
       SUM(CASE WHEN is_won THEN 1 ELSE 0 END) AS won,
       ROUND(100.0 * SUM(CASE WHEN is_won THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN is_closed THEN 1 ELSE 0 END), 0), 1) AS win_rate_pct,
       ROUND(AVG(CASE WHEN is_closed THEN DATEDIFF('day', created_at, close_date) END), 1) AS avg_cycle_days,
       COALESCE(SUM(CASE WHEN is_won THEN amount END), 0) AS won_value,
       COALESCE(SUM(CASE WHEN NOT is_closed THEN amount END), 0) AS open_pipeline
FROM opportunities GROUP BY source_tier ORDER BY source_tier;

CREATE OR REPLACE VIEW v_open_pipeline_by_stage AS
SELECT o.stage, s.stage_order, COUNT(*) AS opportunities, COALESCE(SUM(o.amount), 0) AS amount
FROM opportunities o JOIN v_stage_order s ON s.stage = o.stage
WHERE NOT o.is_closed GROUP BY o.stage, s.stage_order ORDER BY s.stage_order;
