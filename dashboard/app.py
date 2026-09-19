"""Streamlit dashboard. Reads DuckDB reporting views only. Three tabs: CPQ Operations, Account Prioritization, Data Quality."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import settings  # noqa: E402
from src.db import connect  # noqa: E402
from src.policy import get_policy  # noqa: E402

st.set_page_config(page_title="GTM Revenue Operations Engine", layout="wide")
PALETTE = ["#2f6fd6", "#1a9a5a", "#e07b00", "#7c3aed", "#d64545", "#5f6b7a"]


@st.cache_data(ttl=30)
def q(sql: str) -> pd.DataFrame:
    con = connect()
    try:
        return con.execute(sql).df()
    finally:
        con.close()


if not settings.duckdb_file.exists():
    st.error("No database yet. Run `python -m src.main run-all` first.")
    st.stop()

policy = get_policy()
st.title("GTM Revenue Operations Engine")
st.caption(f"Deterministic pricing, approvals and account prioritization · policy version {policy.version} · "
           f"Salesforce {'enabled' if settings.sf_enabled else 'mock'} · AI drafting {'on' if settings.ai_enabled else 'off (templates)'}")

# Deep link: ?view=cpq | gtm | dq renders a single section (used for screenshots and sharing); default is tabs.
_VIEW = st.query_params.get("view")
if _VIEW in ("cpq", "gtm", "pipe", "dq"):
    from contextlib import nullcontext
    _single = {"cpq": "CPQ Operations", "gtm": "Account Prioritization", "pipe": "Pipeline", "dq": "Data Quality"}[_VIEW]
    st.subheader(_single)
    st.markdown("<style>[data-testid='stExpander']{display:none}</style>", unsafe_allow_html=True)
    tab_cpq = nullcontext() if _VIEW == "cpq" else st.expander("CPQ Operations", expanded=False)
    tab_gtm = nullcontext() if _VIEW == "gtm" else st.expander("Account Prioritization", expanded=False)
    tab_pipe = nullcontext() if _VIEW == "pipe" else st.expander("Pipeline", expanded=False)
    tab_dq = nullcontext() if _VIEW == "dq" else st.expander("Data Quality", expanded=False)
else:
    tab_cpq, tab_gtm, tab_pipe, tab_dq = st.tabs(["CPQ Operations", "Account Prioritization", "Pipeline", "Data Quality"])

# ------------------------------------------------------------------ CPQ
with tab_cpq:
    s = q("SELECT * FROM v_cpq_summary").iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total quotes", int(s.total_quotes))
    c2.metric("Auto-approve rate", f"{s.auto_approve_rate_pct or 0:.0f}%")
    c3.metric("Pending approval", int(s.pending_approval))
    c4.metric("Avg pending age (days)", f"{s.avg_pending_age_days or 0:.1f}", delta=f"SLA {int(s.pending_sla_days)}d", delta_color="off")
    c5.metric("Failed validation", int(s.failed_validation))

    left, right = st.columns(2)
    with left:
        st.subheader("Quotes by approval route")
        df = q("SELECT * FROM v_quotes_by_route")
        st.plotly_chart(px.bar(df, x="quotes", y="route", orientation="h", color_discrete_sequence=PALETTE), use_container_width=True)
    with right:
        st.subheader("Policy exceptions by rule")
        df = q("SELECT * FROM v_exceptions_by_reason")
        st.plotly_chart(px.bar(df, x="rule_triggered", y="occurrences", color_discrete_sequence=[PALETTE[2]]), use_container_width=True)

    st.subheader("Discount distribution")
    df = q("SELECT * FROM v_discount_distribution")
    fig = px.histogram(df, x="discount_percent", color="approval_status", nbins=20, barmode="stack", color_discrete_sequence=PALETTE)
    fig.add_vline(x=policy.discount.standard_limit, line_dash="dash", annotation_text="standard limit")
    fig.add_vline(x=policy.discount.manager_limit, line_dash="dash", annotation_text="manager limit")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Quote-to-cash (v2)")
    q2c = q("SELECT * FROM v_quote_to_cash").iloc[0]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Approved (policy + human)", int(q2c.approved_quotes))
    k2.metric("Human approved", int(q2c.human_approved))
    k3.metric("Rejected", int(q2c.rejected))
    k4.metric("Reconciled with ERP", int(q2c.reconciled), delta=f"{int(q2c.failed_reconciliation)} failed", delta_color="inverse")
    k5.metric("Reconciled value", f"${float(q2c.reconciled_value):,.0f}")
    left2, right2 = st.columns(2)
    with left2:
        st.caption("Sales orders handed to the ERP (mock NetSuite)")
        st.dataframe(q("SELECT quote_id, account_name, sales_order_id, status, accepted_total, net_contract_value, sent_at FROM v_erp_orders LIMIT 25"),
                     use_container_width=True, hide_index=True)
    with right2:
        st.caption("Human decisions recorded in Salesforce")
        st.dataframe(q("SELECT quote_id, account_name, approval_status, approver, decision_at, rejection_reason FROM v_human_decisions LIMIT 25"),
                     use_container_width=True, hide_index=True)

    st.subheader("Recent quote decisions")
    st.dataframe(q("SELECT quote_id, account_name, product_id, monthly_commitment, contract_term_months, discount_percent, payment_terms, "
                   "annual_contract_value, approval_status, approver, approval_route, erp_status, exception_reason FROM quotes ORDER BY created_at DESC LIMIT 50"),
                 use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ GTM
with tab_gtm:
    tiers = q("SELECT * FROM v_accounts_by_tier")
    c1, c2, c3, c4 = st.columns(4)
    for col, tier in zip((c1, c2, c3), ("Tier 1", "Tier 2", "Tier 3")):
        row = tiers[tiers.account_tier == tier]
        col.metric(tier, int(row.accounts.iloc[0]) if len(row) else 0)
    no_task = q("SELECT COUNT(*) AS n FROM v_tier1_without_task").n.iloc[0]
    c4.metric("Tier 1 without open task", int(no_task), delta="should be 0", delta_color="off")

    left, right = st.columns(2)
    with left:
        st.subheader("Priority score distribution")
        df = q("SELECT priority_score, account_tier FROM account_scores")
        fig = px.histogram(df, x="priority_score", color="account_tier", nbins=25, color_discrete_sequence=PALETTE)
        fig.add_vline(x=policy.scoring.tiers.tier_1, line_dash="dash", annotation_text="Tier 1")
        fig.add_vline(x=policy.scoring.tiers.tier_2, line_dash="dash", annotation_text="Tier 2")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Signal sources (Clay, HubSpot, web, telemetry)")
        df = q("SELECT * FROM v_signal_sources")
        st.plotly_chart(px.pie(df, names="signal_source", values="signals", hole=0.45, color_discrete_sequence=PALETTE), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Tasks by owner")
        df = q("SELECT * FROM v_tasks_by_owner")
        if len(df):
            st.plotly_chart(px.bar(df, x="owner", y="tasks", color="priority", barmode="stack", color_discrete_sequence=PALETTE), use_container_width=True)
    with right:
        st.subheader("Draft source")
        df = q("SELECT * FROM v_draft_sources")
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption("`template` = deterministic text; `claude` = optional AI-assisted draft. Scores are never AI-generated.")

    st.subheader("Top accounts")
    st.dataframe(q("SELECT * FROM v_top_accounts LIMIT 30"), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ Pipeline (v2)
with tab_pipe:
    funnel = q("SELECT * FROM v_funnel")
    bott = q("SELECT * FROM v_bottleneck")
    by_tier = q("SELECT * FROM v_conversion_by_tier")
    b = bott[bott.bottleneck == True]  # noqa: E712
    c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1.8])
    c1.metric("Opportunities", int(funnel.opportunities.iloc[0]) if len(funnel) else 0)
    c2.metric("Closed won", int(funnel[funnel.stage == "Closed Won"].opportunities.iloc[0]) if len(funnel) else 0)
    c3.metric("Open pipeline", f"${float(by_tier.open_pipeline.sum()):,.0f}" if len(by_tier) else "$0")
    if len(b):
        c4.metric("Bottleneck", f"{b.from_stage.iloc[0]} → {b.to_stage.iloc[0]}", delta=f"{float(b.step_conversion_pct.iloc[0]):.0f}% convert", delta_color="inverse")

    left, right = st.columns(2)
    with left:
        st.subheader("Stage funnel")
        fig = px.funnel(funnel, x="opportunities", y="stage", color_discrete_sequence=[PALETTE[0]])
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Step conversion (drop-off by stage)")
        bott["step"] = bott.from_stage + " → " + bott.to_stage
        bott["colour"] = bott.bottleneck.map({True: "bottleneck", False: "normal"})
        fig = px.bar(bott, x="step", y="step_conversion_pct", color="colour",
                     color_discrete_map={"bottleneck": PALETTE[4], "normal": PALETTE[0]}, text="dropped",
                     category_orders={"step": list(bott.step)})
        fig.update_layout(yaxis_title="% converting to next stage", xaxis_title="", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Conversion by account tier")
        st.dataframe(by_tier, use_container_width=True, hide_index=True)
        st.caption("`source_tier` is the account tier when the opportunity was created. Win rate is over closed opportunities.")
    with right:
        st.subheader("Median days in stage")
        cyc = q("SELECT stage, median_days, avg_days, lost_from_here FROM v_stage_cycle")
        st.plotly_chart(px.bar(cyc, x="stage", y="median_days", color_discrete_sequence=[PALETTE[2]]), use_container_width=True)

    st.subheader("Open pipeline by stage")
    st.dataframe(q("SELECT stage, opportunities, amount FROM v_open_pipeline_by_stage"), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ DQ
with tab_dq:
    dq = q("SELECT * FROM v_dq_latest")
    if dq.empty:
        st.info("No DQ run yet. Run `python -m src.main dq`.")
    else:
        errors = dq[(dq.severity == "error") & (dq.row_count > 0)]
        warns = dq[(dq.severity == "warn") & (dq.row_count > 0)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Error checks failing", len(errors))
        c2.metric("Warning checks firing", len(warns))
        c3.metric("Last run", str(dq.ran_at.iloc[0])[:19])
        st.dataframe(dq, use_container_width=True, hide_index=True)

    st.subheader("Integration runs")
    st.dataframe(q("SELECT * FROM v_integration_status"), use_container_width=True, hide_index=True)
    st.subheader("Recent failures and retries")
    st.dataframe(q("SELECT workflow_name, record_type, record_id, status, retry_count, error_message, started_at, correlation_id "
                   "FROM integration_log WHERE status NOT IN ('STARTED','SUCCESS') ORDER BY started_at DESC LIMIT 50"),
                 use_container_width=True, hide_index=True)
