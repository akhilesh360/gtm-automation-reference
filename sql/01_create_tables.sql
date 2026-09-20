-- Snowflake-compatible DDL where practical. DuckDB-only syntax is isolated in 02_load_raw_data.sql.

CREATE TABLE IF NOT EXISTS accounts (
    account_id      VARCHAR PRIMARY KEY,
    account_name    VARCHAR NOT NULL,
    domain          VARCHAR,
    industry        VARCHAR,
    employee_count  INTEGER,
    funding_stage   VARCHAR,
    account_owner   VARCHAR,
    sf_account_id   VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS account_enrichment (
    enrichment_id           VARCHAR PRIMARY KEY,
    account_id              VARCHAR,
    domain                  VARCHAR,
    employee_count          INTEGER,
    funding_stage           VARCHAR,
    funding_amount_usd      DECIMAL(14,2),
    tech_stack              VARCHAR,
    open_ml_roles           INTEGER,
    open_data_infra_roles   INTEGER,
    company_summary         VARCHAR,
    personalization_hook    VARCHAR,
    enrichment_source       VARCHAR,
    enriched_at             TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intent_signals (
    signal_id        VARCHAR PRIMARY KEY,
    account_id       VARCHAR NOT NULL,
    signal_type      VARCHAR NOT NULL,
    signal_value     DECIMAL(10,2),
    signal_source    VARCHAR,
    signal_timestamp TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_signals (
    usage_id        VARCHAR PRIMARY KEY,
    account_id      VARCHAR NOT NULL,
    month           DATE,
    api_calls       BIGINT,
    active_users    INTEGER,
    mom_growth_pct  DECIMAL(6,2)
);

CREATE TABLE IF NOT EXISTS products (
    product_id              VARCHAR PRIMARY KEY,
    product_name            VARCHAR NOT NULL,
    pricing_model           VARCHAR NOT NULL,
    list_price_monthly      DECIMAL(12,2) NOT NULL,
    included_units          BIGINT,
    overage_price_per_unit  DECIMAL(14,10)
);

CREATE TABLE IF NOT EXISTS quote_requests (
    quote_id              VARCHAR PRIMARY KEY,
    account_id            VARCHAR NOT NULL,
    account_name          VARCHAR,
    product_id            VARCHAR NOT NULL,
    monthly_commitment    DECIMAL(12,2),
    quantity              INTEGER,
    contract_term_months  INTEGER,
    discount_percent      DECIMAL(5,2),
    payment_terms         VARCHAR,
    custom_pricing        BOOLEAN,
    forecasted_units      BIGINT,
    custom_overage_rate   DECIMAL(14,10),
    requested_at          TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quotes (
    quote_id               VARCHAR PRIMARY KEY,
    account_id             VARCHAR NOT NULL,
    account_name           VARCHAR,
    product_id             VARCHAR NOT NULL,
    monthly_commitment     DECIMAL(12,2),
    quantity               INTEGER,
    contract_term_months   INTEGER,
    discount_percent       DECIMAL(5,2),
    payment_terms          VARCHAR,
    custom_pricing         BOOLEAN,
    forecasted_units       BIGINT,
    custom_overage_rate    DECIMAL(14,10),
    overage_units          BIGINT,
    monthly_overage        DECIMAL(12,2),
    effective_list_price   DECIMAL(12,2),
    gross_contract_value   DECIMAL(14,2),
    discount_amount        DECIMAL(14,2),
    net_contract_value     DECIMAL(14,2),
    annual_contract_value  DECIMAL(14,2),
    approval_status        VARCHAR,
    approval_route         VARCHAR,
    exception_reason       VARCHAR,
    policy_version         VARCHAR,
    sf_quote_id            VARCHAR,
    created_at             TIMESTAMP,
    evaluated_at           TIMESTAMP,
    correlation_id         VARCHAR,
    -- v2: human decision + ERP handoff
    approver               VARCHAR,
    decision_at            TIMESTAMP,
    rejection_reason       VARCHAR,
    erp_order_id           VARCHAR,
    erp_status             VARCHAR DEFAULT 'Not Sent',
    erp_sent_at            TIMESTAMP
);

CREATE TABLE IF NOT EXISTS erp_orders (
    order_id         VARCHAR PRIMARY KEY,
    quote_id         VARCHAR NOT NULL,
    sales_order_id   VARCHAR,
    status           VARCHAR NOT NULL,
    payload_json     VARCHAR,
    accepted_total   DECIMAL(14,2),
    sent_at          TIMESTAMP,
    reconciled_at    TIMESTAMP,
    error_message    VARCHAR,
    correlation_id   VARCHAR
);

CREATE TABLE IF NOT EXISTS approval_audit (
    audit_id            VARCHAR PRIMARY KEY,
    quote_id            VARCHAR NOT NULL,
    rule_triggered      VARCHAR NOT NULL,
    requested_discount  DECIMAL(5,2),
    required_approver   VARCHAR,
    decision            VARCHAR NOT NULL,
    decision_reason     VARCHAR,
    decision_timestamp  TIMESTAMP,
    approver            VARCHAR,
    policy_version      VARCHAR,
    correlation_id      VARCHAR
);

CREATE TABLE IF NOT EXISTS account_scores (
    score_id                VARCHAR PRIMARY KEY,
    account_id              VARCHAR NOT NULL,
    intent_score            DECIMAL(5,2),
    engagement_score        DECIMAL(5,2),
    firmographic_fit_score  DECIMAL(5,2),
    usage_score             DECIMAL(5,2),
    priority_score          DECIMAL(5,2),
    account_tier            VARCHAR,
    scoring_reason          VARCHAR,
    narrative               VARCHAR,
    task_description        VARCHAR,
    outbound_draft          VARCHAR,
    draft_source            VARCHAR,
    policy_version          VARCHAR,
    scored_at               TIMESTAMP,
    correlation_id          VARCHAR
);

CREATE TABLE IF NOT EXISTS sales_tasks (
    task_id      VARCHAR PRIMARY KEY,
    account_id   VARCHAR NOT NULL,
    owner        VARCHAR,
    subject      VARCHAR,
    description  VARCHAR,
    priority     VARCHAR,
    status       VARCHAR,
    sf_task_id   VARCHAR,
    created_at   TIMESTAMP,
    updated_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS integration_log (
    log_id          VARCHAR PRIMARY KEY,
    workflow_name   VARCHAR NOT NULL,
    record_type     VARCHAR,
    record_id       VARCHAR,
    status          VARCHAR NOT NULL,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    error_message   VARCHAR,
    retry_count     INTEGER DEFAULT 0,
    correlation_id  VARCHAR
);

CREATE TABLE IF NOT EXISTS dq_results (
    run_id      VARCHAR,
    check_name  VARCHAR,
    severity    VARCHAR,
    row_count   INTEGER,
    sample_ids  VARCHAR,
    ran_at      TIMESTAMP
);

-- v2: opportunities and stage history
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id     VARCHAR PRIMARY KEY,
    account_id         VARCHAR NOT NULL,
    name               VARCHAR,
    amount             DECIMAL(14,2),
    stage              VARCHAR,
    created_at         DATE,
    close_date         DATE,
    is_closed          BOOLEAN,
    is_won             BOOLEAN,
    source_tier        VARCHAR,
    sf_opportunity_id  VARCHAR
);

CREATE TABLE IF NOT EXISTS opportunity_stage_history (
    history_id          VARCHAR PRIMARY KEY,
    opportunity_id      VARCHAR NOT NULL,
    from_stage          VARCHAR,
    to_stage            VARCHAR,
    changed_at          TIMESTAMP,
    days_in_from_stage  INTEGER
);

-- v2: forecast snapshots (one row per snapshot date x close month x tier)
CREATE TABLE IF NOT EXISTS forecast_snapshots (
    snapshot_id        VARCHAR PRIMARY KEY,
    snapshot_date      DATE,
    close_month        DATE,
    account_tier       VARCHAR,
    open_opportunities INTEGER,
    open_pipeline      DECIMAL(14,2),
    weighted_forecast  DECIMAL(14,2),
    closed_won_actual  DECIMAL(14,2),
    policy_version     VARCHAR,
    correlation_id     VARCHAR
);

-- v2: outbound sequence enrollments
CREATE TABLE IF NOT EXISTS sequence_enrollments (
    enrollment_id     VARCHAR PRIMARY KEY,
    account_id        VARCHAR NOT NULL,
    sequence_name     VARCHAR NOT NULL,
    enrolled_at       TIMESTAMP,
    status            VARCHAR,
    step              INTEGER,
    first_touch_draft VARCHAR,
    last_activity_at  TIMESTAMP,
    correlation_id    VARCHAR
);

-- v2: AI-assisted (or template) account research
CREATE TABLE IF NOT EXISTS account_research (
    research_id     VARCHAR PRIMARY KEY,
    account_id      VARCHAR NOT NULL,
    brief           VARCHAR,
    outbound_draft  VARCHAR,
    talking_points  VARCHAR,
    source          VARCHAR,
    tool_calls      INTEGER,
    researched_at   TIMESTAMP,
    correlation_id  VARCHAR
);
