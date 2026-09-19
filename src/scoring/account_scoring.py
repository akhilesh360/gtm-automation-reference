"""Deterministic sub-scores and priority score. Weights and window come from policy.yaml."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import duckdb

from src.db import run_sql_file
from src.policy import Policy

AI_INDUSTRIES = {"AI/ML"}
ADJACENT_INDUSTRIES = {"SaaS", "Developer Tools", "Fintech"}
BEST_STAGES = {"Series A", "Series B", "Series C"}


@dataclass
class ScoreFacts:
    account_id: str
    account_name: str
    industry: Optional[str]
    employee_count: Optional[int]
    funding_stage: Optional[str]
    account_owner: Optional[str]
    pricing_page_visits: float
    demo_requests: float
    ml_job_postings: float
    funding_events: float
    oss_interest: float
    website_visits: float
    email_engagements: float
    mom_growth_pct: Optional[float]
    active_users: Optional[int]
    last_signal_at: Optional[str]
    company_summary: Optional[str] = None
    personalization_hook: Optional[str] = None
    tech_stack: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SubScores:
    intent: float
    engagement: float
    usage: float
    firmographic: float


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 2)


def intent_score(f: ScoreFacts) -> float:
    return _clamp(f.demo_requests * 40 + min(f.pricing_page_visits * 10, 40) + min(f.ml_job_postings * 10, 20)
                  + f.funding_events * 15 + min(f.oss_interest * 5, 10))


def engagement_score(f: ScoreFacts) -> float:
    return _clamp(min(f.website_visits * 2, 50) + min(f.email_engagements * 10, 50))


def usage_score(f: ScoreFacts) -> float:
    growth = max(f.mom_growth_pct or 0.0, 0.0)
    growth_component = min(min(growth, 50) * 1.75, 80)
    users_component = min((f.active_users or 0) / 10, 20)
    return _clamp(growth_component + users_component)


def firmographic_score(f: ScoreFacts) -> float:
    ind = 40 if f.industry in AI_INDUSTRIES else 30 if f.industry in ADJACENT_INDUSTRIES else 10
    emp = f.employee_count or 0
    size = 30 if 50 <= emp <= 2000 else 15 if 20 <= emp < 50 else 10 if 2000 < emp <= 5000 else 5
    stage = 30 if f.funding_stage in BEST_STAGES else 20 if f.funding_stage == "Series D" else 15 if f.funding_stage == "Seed" else 10
    return _clamp(ind + size + stage)


def sub_scores(f: ScoreFacts) -> SubScores:
    return SubScores(intent_score(f), engagement_score(f), usage_score(f), firmographic_score(f))


def priority_score(s: SubScores, policy: Policy) -> float:
    w = policy.scoring.weights
    return round(s.intent * w.intent + s.usage * w.usage + s.engagement * w.engagement + s.firmographic * w.firmographic, 2)


def fetch_facts(con: duckdb.DuckDBPyConnection, policy: Policy) -> list[ScoreFacts]:
    run_sql_file(con, "03_account_scoring.sql", {"window_days": policy.scoring.window_days})
    rows = con.execute(
        """
        SELECT a.account_id, a.account_name, a.industry,
               COALESCE(e.employee_count, a.employee_count) AS employee_count,
               COALESCE(e.funding_stage, a.funding_stage) AS funding_stage,
               a.account_owner,
               g.pricing_page_visits, g.demo_requests, g.ml_job_postings, g.funding_events, g.oss_interest,
               g.website_visits, g.email_engagements,
               u.mom_growth_pct, u.active_users, g.last_signal_at,
               e.company_summary, e.personalization_hook, e.tech_stack
        FROM accounts a
        JOIN v_signal_aggregates g ON g.account_id = a.account_id
        LEFT JOIN v_latest_usage u ON u.account_id = a.account_id
        LEFT JOIN account_enrichment e ON e.account_id = a.account_id
        ORDER BY a.account_id
        """
    ).fetchall()
    facts = []
    for r in rows:
        facts.append(ScoreFacts(
            account_id=r[0], account_name=r[1], industry=r[2], employee_count=r[3], funding_stage=r[4], account_owner=r[5],
            pricing_page_visits=float(r[6] or 0), demo_requests=float(r[7] or 0), ml_job_postings=float(r[8] or 0),
            funding_events=float(r[9] or 0), oss_interest=float(r[10] or 0), website_visits=float(r[11] or 0),
            email_engagements=float(r[12] or 0), mom_growth_pct=float(r[13]) if r[13] is not None else None,
            active_users=int(r[14]) if r[14] is not None else None, last_signal_at=str(r[15]) if r[15] else None,
            company_summary=r[16], personalization_hook=r[17], tech_stack=r[18],
        ))
    return facts
