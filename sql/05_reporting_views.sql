-- Reporting views consumed by the Streamlit dashboard. Parameters: $pending_sla_days

CREATE OR REPLACE VIEW v_cpq_summary AS
SELECT
    COUNT(*)                                                                AS total_quotes,
    SUM(CASE WHEN approval_status = 'Auto-Approved' THEN 1 ELSE 0 END)      AS auto_approved,
    SUM(CASE WHEN approval_status = 'Pending Approval' THEN 1 ELSE 0 END)   AS pending_approval,
    SUM(CASE WHEN approval_status = 'Failed Validation' THEN 1 ELSE 0 END)  AS failed_validation,
    ROUND(100.0 * SUM(CASE WHEN approval_status = 'Auto-Approved' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS auto_approve_rate_pct,
    ROUND(AVG(CASE WHEN approval_status = 'Pending Approval'
                   THEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - created_at)) / 86400.0 END), 2) AS avg_pending_age_days,
    $pending_sla_days                                                       AS pending_sla_days,
    MAX(policy_version)                                                     AS policy_version
FROM quotes;

CREATE OR REPLACE VIEW v_quotes_by_route AS
SELECT COALESCE(NULLIF(approval_route, ''), approval_status) AS route, COUNT(*) AS quotes
FROM quotes GROUP BY 1 ORDER BY quotes DESC;

CREATE OR REPLACE VIEW v_exceptions_by_reason AS
SELECT rule_triggered, COUNT(*) AS occurrences
FROM approval_audit
WHERE rule_triggered NOT IN ('STANDARD_POLICY')
GROUP BY 1 ORDER BY occurrences DESC;

CREATE OR REPLACE VIEW v_discount_distribution AS
SELECT quote_id, account_name, discount_percent, approval_status, annual_contract_value FROM quotes;

CREATE OR REPLACE VIEW v_accounts_by_tier AS
SELECT account_tier, COUNT(*) AS accounts, ROUND(AVG(priority_score), 1) AS avg_priority
FROM account_scores GROUP BY 1 ORDER BY 1;

CREATE OR REPLACE VIEW v_tier1_without_task AS
SELECT a.account_id, a.account_name, a.account_owner, s.priority_score
FROM account_scores s
JOIN accounts a ON a.account_id = s.account_id
LEFT JOIN sales_tasks t ON t.account_id = s.account_id AND t.priority = 'High' AND t.status IN ('open', 'created')
WHERE s.account_tier = 'Tier 1' AND t.task_id IS NULL;

CREATE OR REPLACE VIEW v_signal_sources AS
SELECT signal_source, COUNT(*) AS signals FROM intent_signals GROUP BY 1 ORDER BY signals DESC;

CREATE OR REPLACE VIEW v_tasks_by_owner AS
SELECT owner, priority, status, COUNT(*) AS tasks FROM sales_tasks GROUP BY 1, 2, 3 ORDER BY 1;

CREATE OR REPLACE VIEW v_draft_sources AS
SELECT draft_source, COUNT(*) AS accounts FROM account_scores WHERE draft_source IS NOT NULL GROUP BY 1;

CREATE OR REPLACE VIEW v_top_accounts AS
SELECT a.account_name, a.account_owner, s.priority_score, s.account_tier,
       s.intent_score, s.usage_score, s.engagement_score, s.firmographic_fit_score, s.scoring_reason, s.narrative
FROM account_scores s JOIN accounts a ON a.account_id = s.account_id
ORDER BY s.priority_score DESC;

CREATE OR REPLACE VIEW v_integration_status AS
SELECT workflow_name, status, COUNT(*) AS runs, MAX(started_at) AS last_run
FROM integration_log GROUP BY 1, 2 ORDER BY 1, 2;

CREATE OR REPLACE VIEW v_dq_latest AS
SELECT check_name, severity, row_count, sample_ids, ran_at
FROM dq_results
WHERE run_id = (SELECT run_id FROM dq_results ORDER BY ran_at DESC LIMIT 1)
ORDER BY severity, check_name;

-- v2: quote-to-cash
CREATE OR REPLACE VIEW v_quote_to_cash AS
SELECT
    SUM(CASE WHEN approval_status IN ('Auto-Approved', 'Approved') THEN 1 ELSE 0 END) AS approved_quotes,
    SUM(CASE WHEN approval_status = 'Approved' THEN 1 ELSE 0 END)                    AS human_approved,
    SUM(CASE WHEN approval_status = 'Rejected' THEN 1 ELSE 0 END)                    AS rejected,
    SUM(CASE WHEN erp_status = 'Sent' THEN 1 ELSE 0 END)                             AS sent_to_erp,
    SUM(CASE WHEN erp_status = 'Reconciled' THEN 1 ELSE 0 END)                       AS reconciled,
    SUM(CASE WHEN erp_status = 'Failed' THEN 1 ELSE 0 END)                           AS failed_reconciliation,
    COALESCE(SUM(CASE WHEN erp_status = 'Reconciled' THEN net_contract_value END), 0) AS reconciled_value
FROM quotes;

CREATE OR REPLACE VIEW v_erp_orders AS
SELECT o.order_id, o.quote_id, q.account_name, o.sales_order_id, o.status, o.accepted_total, q.net_contract_value,
       o.sent_at, o.reconciled_at, o.error_message
FROM erp_orders o JOIN quotes q ON q.quote_id = o.quote_id
ORDER BY o.sent_at DESC;

CREATE OR REPLACE VIEW v_human_decisions AS
SELECT quote_id, account_name, approval_status, approver, decision_at, rejection_reason, approval_route
FROM quotes WHERE approver IS NOT NULL ORDER BY decision_at DESC;
