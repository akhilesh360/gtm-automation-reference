"""Outbound sequence enrollment. Tier 1 and Tier 2 accounts are enrolled once; an active enrollment is never duplicated.

Status is derived deterministically from signals in v1 of this feature: an account that requested a demo AND
engaged with at least six emails counts as "replied"; everything else stays "active". A real sequencer
(Outreach, Salesloft, HubSpot Sequences) would own status in production; this module owns enrollment and dedupe.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import duckdb

from src.policy import Policy

ACTIVE = ("active", "replied")


def enroll_accounts(con: duckdb.DuckDBPyConnection, policy: Policy, correlation_id: str) -> dict[str, int]:
    seq_for = {"Tier 1": policy.outbound.sequences.get("tier_1"), "Tier 2": policy.outbound.sequences.get("tier_2")}
    rows = con.execute(
        "SELECT s.account_id, s.account_tier, s.outbound_draft, g.demo_requests, g.email_engagements "
        "FROM account_scores s LEFT JOIN v_signal_aggregates g ON g.account_id = s.account_id "
        "WHERE s.account_tier IN ('Tier 1', 'Tier 2') ORDER BY s.priority_score DESC").fetchall()
    now = datetime.now()
    counts = {"enrolled": 0, "already_active": 0, "replied": 0}
    for account_id, tier, draft, demo_requests, email_engagements in rows:
        seq = seq_for.get(tier)
        if not seq:
            continue
        active = con.execute(
            f"SELECT COUNT(*) FROM sequence_enrollments WHERE account_id = ? AND status IN {ACTIVE}", [account_id]).fetchone()[0]
        if active >= policy.outbound.max_active_per_account:
            counts["already_active"] += 1
            continue
        status = "replied" if (demo_requests or 0) > 0 and (email_engagements or 0) >= 6 else "active"
        con.execute("INSERT INTO sequence_enrollments VALUES (?,?,?,?,?,?,?,?,?)",
                    [f"SEQ-{uuid.uuid4().hex[:8].upper()}", account_id, seq, now, status, 1, draft, now, correlation_id])
        counts["enrolled"] += 1
        if status == "replied":
            counts["replied"] += 1
    return counts
