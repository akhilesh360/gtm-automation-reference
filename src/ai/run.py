"""Draft stage: fill narrative / task_description / outbound_draft for Tier 1 accounts (template for the rest)."""
from __future__ import annotations

from typing import Optional

import duckdb

from src.ai.drafter import DraftFacts, draft, template_draft, DraftResult
from src.monitoring.logger import get_logger

log = get_logger()


def _facts_for(con: duckdb.DuckDBPyConnection, account_id: str) -> Optional[DraftFacts]:
    r = con.execute(
        """SELECT a.account_id, a.account_name, a.account_owner, s.account_tier, s.priority_score, s.intent_score, s.usage_score,
                  s.engagement_score, s.firmographic_fit_score, s.scoring_reason, a.industry,
                  COALESCE(e.employee_count, a.employee_count), COALESCE(e.funding_stage, a.funding_stage),
                  u.mom_growth_pct, g.pricing_page_visits, g.demo_requests, g.ml_job_postings, g.email_engagements,
                  e.company_summary, e.personalization_hook, e.tech_stack
           FROM account_scores s
           JOIN accounts a ON a.account_id = s.account_id
           LEFT JOIN account_enrichment e ON e.account_id = a.account_id
           LEFT JOIN v_latest_usage u ON u.account_id = a.account_id
           LEFT JOIN v_signal_aggregates g ON g.account_id = a.account_id
           WHERE s.account_id = ?""", [account_id]).fetchone()
    if not r:
        return None
    quotes = con.execute("SELECT quote_id, approval_status, annual_contract_value FROM quotes WHERE account_id = ?", [account_id]).fetchall()
    return DraftFacts(
        account_id=r[0], account_name=r[1], account_owner=r[2], account_tier=r[3], priority_score=float(r[4]),
        intent_score=float(r[5]), usage_score=float(r[6]), engagement_score=float(r[7]), firmographic_fit_score=float(r[8]),
        scoring_reason=r[9], industry=r[10], employee_count=r[11], funding_stage=r[12],
        mom_growth_pct=float(r[13]) if r[13] is not None else None, pricing_page_visits=float(r[14] or 0),
        demo_requests=float(r[15] or 0), ml_job_postings=float(r[16] or 0), email_engagements=float(r[17] or 0),
        company_summary=r[18], personalization_hook=r[19], tech_stack=r[20],
        open_quotes=[{"quote_id": q[0], "status": q[1], "acv": float(q[2]) if q[2] is not None else None} for q in quotes] or None,
    )


def _store(con: duckdb.DuckDBPyConnection, account_id: str, res: DraftResult) -> None:
    con.execute(
        "UPDATE account_scores SET narrative = ?, task_description = ?, outbound_draft = ?, draft_source = ? WHERE account_id = ?",
        [res.draft.narrative, res.draft.task_description, res.draft.outbound_draft, res.source, account_id])
    con.execute("UPDATE sales_tasks SET description = ? WHERE account_id = ? AND status = 'planned'",
                [res.draft.task_description, account_id])


def draft_all(con: duckdb.DuckDBPyConnection, limit: Optional[int] = None) -> dict[str, int]:
    rows = con.execute("SELECT account_id, account_tier FROM account_scores ORDER BY priority_score DESC").fetchall()
    counts = {"claude": 0, "template": 0}
    ai_calls = 0
    for account_id, tier in rows:
        facts = _facts_for(con, account_id)
        if facts is None:
            continue
        if tier == "Tier 1" and (limit is None or ai_calls < limit):
            res = draft(facts)
            if res.source == "claude":
                ai_calls += 1
        else:
            res = DraftResult(template_draft(facts), "template")
        _store(con, account_id, res)
        counts[res.source] += 1
    return counts


def research_one(con: duckdb.DuckDBPyConnection, account_id: str) -> Optional[DraftResult]:
    facts = _facts_for(con, account_id)
    if facts is None:
        return None
    res = draft(facts)
    _store(con, account_id, res)
    return res
