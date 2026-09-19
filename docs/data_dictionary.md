# Data dictionary

All tables live in DuckDB (`data/gtm.duckdb`), created by `sql/01_create_tables.sql`. DDL is Snowflake-compatible except CSV loading (`02_load_raw_data.sql`).

## Source tables (loaded from `data/raw/*.csv`)

| Table | Grain | Source | Key columns |
|---|---|---|---|
| `accounts` | one row per account | `accounts.csv` (CRM export shape) | `account_id` PK, `domain`, `industry`, `employee_count`, `funding_stage`, `account_owner`, `sf_account_id` (set after sync) |
| `account_enrichment` | one row per enriched account | `clay_enrichment.csv` (Clay-shaped export) | `enrichment_id` PK, `account_id`, `employee_count`, `funding_stage`, `funding_amount_usd`, `tech_stack`, `open_ml_roles`, `open_data_infra_roles`, `company_summary`, `personalization_hook`, `enrichment_source` |
| `intent_signals` | one row per signal event | `intent_signals.csv` + HubSpot events mapped by `load_hubspot.py` | `signal_id` PK, `account_id`, `signal_type`, `signal_value`, `signal_source` (`web_analytics`, `clay`, `hubspot`, `product_telemetry`, `job_boards`, `news_feed`, `email_platform`), `signal_timestamp` |
| `usage_signals` | one row per account per month | `usage_signals.csv` (product telemetry) | `usage_id` PK, `account_id`, `month`, `api_calls`, `active_users`, `mom_growth_pct` |
| `products` | one row per sellable product | `products.csv` | `product_id` PK, `pricing_model` (`usage` / `subscription`), `list_price_monthly`, `included_units`, `overage_price_per_unit` |
| `quote_requests` | one row per requested quote | `quote_requests.csv` | `quote_id` PK, `account_id`, `product_id`, `monthly_commitment`, `contract_term_months`, `discount_percent`, `payment_terms`, `custom_pricing`, `forecasted_units`, `custom_overage_rate`, `requested_at` |

Signal types: `website_visit`, `pricing_page_visit`, `demo_request`, `job_posting_ml_engineer`, `funding_event`, `product_usage_growth`, `email_engagement`, `open_source_model_interest`.

HubSpot mapping (`src/ingestion/load_hubspot.py`): `email_open`/`email_click` → `email_engagement`; `meeting_booked` → `demo_request`; `form_submit` on a "Contact sales" campaign → `demo_request`, otherwise `website_visit`; `page_view` on a pricing campaign → `pricing_page_visit`, otherwise `website_visit`.

## Decision tables (written by the Python engine)

| Table | Grain | Written by | Notes |
|---|---|---|---|
| `quotes` | one row per evaluated quote | `src/cpq/audit.py` | Pricing outputs (`overage_units`, `monthly_overage`, `effective_list_price`, `gross_contract_value`, `discount_amount`, `net_contract_value`, `annual_contract_value`) and the decision (`approval_status`, `approval_route`, `exception_reason`, `policy_version`). `sf_quote_id` set after sync. |
| `approval_audit` | ≥ 1 row per quote decision | `src/cpq/audit.py` | One row per rule: `STANDARD_POLICY`, `DISCOUNT_GT_10`, `DISCOUNT_GT_20`, `ACV_GTE_100K`, `NONSTANDARD_TERMS`, `CUSTOM_PRICING`, `FAILED_VALIDATION`. `required_approver` is NULL for `STANDARD_POLICY`. `approver` stays NULL in v1 (human decisions are v2). |
| `account_scores` | one row per account per scoring run | `src/scoring/run.py`, drafts by `src/ai/run.py` | Sub-scores, `priority_score`, `account_tier`, deterministic `scoring_reason` (never overwritten), `narrative`, `task_description`, `outbound_draft`, `draft_source` (`template` / `claude`). |
| `sales_tasks` | one row per planned or created task | `src/scoring/run.py`, updated by `sync_task_outcomes` | `status`: `planned` (Python wrote it) → `open` / `completed` once the Flow-created Salesforce Task is read back. `sf_task_id` NULL until then. Python never creates a Salesforce Task. |

## v2: quote-to-cash

| Table | Grain | Notes |
|---|---|---|
| `quotes` (new columns) | | `approver`, `decision_at`, `rejection_reason` from the human decision in Salesforce; `erp_order_id`, `erp_status` (Not Sent / Sent / Reconciled / Failed), `erp_sent_at` |
| `erp_orders` | one row per sales order sent | `sales_order_id` from the ERP, `status` (SENT / RECONCILED / FAILED_RECONCILIATION / FAILED_VALIDATION), full `payload_json`, `accepted_total`, `error_message` |
| `approval_audit` (new rule) | | `HUMAN_DECISION` rows carry `approver`; policy rows never do |

Views: `v_quote_to_cash`, `v_erp_orders`, `v_human_decisions`. DQ checks: `approved_quotes_without_erp_order` (warn), `erp_orders_not_reconciled` (error).

## v2: opportunities

| Table | Grain | Notes |
|---|---|---|
| `opportunities` | one row per deal | `stage`, `amount`, `close_date`, `is_closed`, `is_won`, `source_tier` (account tier at creation), `sf_opportunity_id` |
| `opportunity_stage_history` | one row per stage transition | `from_stage`, `to_stage`, `changed_at`, `days_in_from_stage` |

Views (`07_funnel.sql`): `v_funnel`, `v_bottleneck`, `v_stage_cycle`, `v_conversion_by_tier`, `v_open_pipeline_by_stage`. DQ checks: `opportunities_without_stage_history`, `closed_won_missing_amount`.

## Operational tables

| Table | Grain | Notes |
|---|---|---|
| `integration_log` | one row per workflow step or API call | `status` ∈ STARTED, SUCCESS, FAILED_VALIDATION, FAILED_API, RETRYING, RECONCILED; `retry_count`; every row carries the run's `correlation_id`. |
| `dq_results` | one row per check per run | `severity` (`warn` / `error`), `row_count`, `sample_ids`. Latest run exposed as `v_dq_latest`. |

## Reporting views (`sql/05_reporting_views.sql`)

`v_cpq_summary`, `v_quotes_by_route`, `v_exceptions_by_reason`, `v_discount_distribution`, `v_accounts_by_tier`, `v_tier1_without_task`, `v_signal_sources`, `v_tasks_by_owner`, `v_draft_sources`, `v_top_accounts`, `v_integration_status`, `v_dq_latest`. The dashboard reads only these.
