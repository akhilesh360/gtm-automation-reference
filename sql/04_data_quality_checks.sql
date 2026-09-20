-- Each block is one check. Thresholds arrive as parameters from Python (policy.yaml); none are hardcoded.
-- Parameters: $pending_sla_days

-- name: accounts_without_domain
SELECT account_id AS id FROM accounts WHERE domain IS NULL OR TRIM(domain) = '';

-- name: duplicate_account_domains
SELECT domain AS id FROM accounts WHERE domain IS NOT NULL GROUP BY domain HAVING COUNT(*) > 1;

-- name: accounts_without_owner
SELECT account_id AS id FROM accounts WHERE account_owner IS NULL OR TRIM(account_owner) = '';

-- name: invalid_discounts
SELECT quote_id AS id FROM quote_requests WHERE discount_percent < 0 OR discount_percent > 100;

-- name: quotes_pending_beyond_sla
SELECT quote_id AS id FROM quotes
WHERE approval_status = 'Pending Approval'
  AND created_at < CURRENT_TIMESTAMP - INTERVAL ($pending_sla_days) DAY;

-- name: tier1_without_open_task
SELECT s.account_id AS id
FROM account_scores s
LEFT JOIN sales_tasks t
  ON t.account_id = s.account_id AND t.priority = 'High' AND t.status IN ('open', 'created')
WHERE s.account_tier = 'Tier 1' AND t.task_id IS NULL;

-- name: scores_without_account
SELECT s.score_id AS id FROM account_scores s LEFT JOIN accounts a ON a.account_id = s.account_id WHERE a.account_id IS NULL;

-- name: signals_without_enrichment
SELECT DISTINCT i.account_id AS id
FROM intent_signals i
LEFT JOIN account_enrichment e ON e.account_id = i.account_id
WHERE e.enrichment_id IS NULL;

-- name: failed_integration_runs_24h
SELECT log_id AS id FROM integration_log
WHERE status IN ('FAILED_VALIDATION', 'FAILED_API')
  AND started_at >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR;

-- name: approved_quotes_without_erp_order
SELECT q.quote_id AS id FROM quotes q
LEFT JOIN erp_orders o ON o.quote_id = q.quote_id
WHERE q.approval_status IN ('Auto-Approved', 'Approved')
  AND o.order_id IS NULL
  AND COALESCE(q.decision_at, q.evaluated_at) < CURRENT_TIMESTAMP - INTERVAL 1 DAY;

-- name: erp_orders_not_reconciled
SELECT order_id AS id FROM erp_orders WHERE status <> 'RECONCILED';

-- name: opportunities_without_stage_history
SELECT o.opportunity_id AS id FROM opportunities o
LEFT JOIN opportunity_stage_history h ON h.opportunity_id = o.opportunity_id
WHERE o.stage <> 'Prospecting' AND h.history_id IS NULL;

-- name: closed_won_missing_amount
SELECT opportunity_id AS id FROM opportunities WHERE is_won AND (amount IS NULL OR amount <= 0);

-- name: duplicate_active_enrollments
SELECT account_id AS id FROM sequence_enrollments WHERE status IN ('active', 'replied') GROUP BY account_id HAVING COUNT(*) > 1;

-- name: tier2_without_enrollment
SELECT s.account_id AS id FROM account_scores s
LEFT JOIN sequence_enrollments e ON e.account_id = s.account_id AND e.status IN ('active', 'replied')
WHERE s.account_tier = 'Tier 2' AND e.enrollment_id IS NULL;
