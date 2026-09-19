"""Score every account, persist account_scores and planned sales_tasks. Python never creates a Salesforce Task."""
from __future__ import annotations

import uuid
from datetime import datetime

import duckdb

from src.policy import Policy
from src.scoring.account_scoring import ScoreFacts, fetch_facts, priority_score, sub_scores
from src.scoring.explain_score import explain
from src.scoring.tiering import assign_tier


def score_all(con: duckdb.DuckDBPyConnection, policy: Policy, correlation_id: str) -> dict[str, int]:
    facts = fetch_facts(con, policy)
    now = datetime.now()
    tiers = {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0}
    con.execute("DELETE FROM account_scores")
    # keep task rows that already have a Salesforce Id so re-runs stay idempotent
    con.execute("DELETE FROM sales_tasks WHERE sf_task_id IS NULL")
    for f in facts:
        s = sub_scores(f)
        p = priority_score(s, policy)
        tier = assign_tier(p, policy)
        tiers[tier] += 1
        reason = explain(f, s, tier)
        score_id = f"SC-{f.account_id[4:]}-{now.strftime('%Y%m%d')}"
        con.execute(
            "INSERT INTO account_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [score_id, f.account_id, s.intent, s.engagement, s.firmographic, s.usage, p, tier, reason,
             None, None, None, None, policy.version, now, correlation_id],
        )
        if tier in ("Tier 1", "Tier 2"):
            existing = con.execute(
                "SELECT task_id FROM sales_tasks WHERE account_id = ? AND priority = ? AND status IN ('planned','open','created')",
                [f.account_id, "High" if tier == "Tier 1" else "Normal"],
            ).fetchone()
            if existing:
                continue
            con.execute(
                "INSERT INTO sales_tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
                [f"TSK-{uuid.uuid4().hex[:8].upper()}", f.account_id, f.account_owner,
                 "High-priority account follow-up" if tier == "Tier 1" else "Add to outbound sequence",
                 reason, "High" if tier == "Tier 1" else "Normal", "planned", None, now, now],
            )
    return tiers


def score_facts_inline(f: ScoreFacts, policy: Policy) -> dict:
    s = sub_scores(f)
    p = priority_score(s, policy)
    tier = assign_tier(p, policy)
    return {"sub_scores": s.__dict__, "priority_score": p, "account_tier": tier, "scoring_reason": explain(f, s, tier)}
