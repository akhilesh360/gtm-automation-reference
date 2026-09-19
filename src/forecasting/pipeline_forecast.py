"""Weighted pipeline forecast: builds the views from policy stage probabilities and stores a dated snapshot."""
from __future__ import annotations

import uuid
from datetime import date, datetime

import duckdb

from src.db import run_sql_file
from src.policy import Policy


def _params(policy: Policy) -> dict:
    sp = policy.forecast.stage_probabilities
    return {"p_prospecting": sp.get("Prospecting", 0.1), "p_discovery": sp.get("Discovery", 0.25),
            "p_proposal": sp.get("Proposal", 0.5), "p_negotiation": sp.get("Negotiation", 0.75)}


def build_views(con: duckdb.DuckDBPyConnection, policy: Policy) -> None:
    run_sql_file(con, "08_forecast.sql", _params(policy))


def snapshot(con: duckdb.DuckDBPyConnection, policy: Policy, correlation_id: str, as_of: date | None = None) -> int:
    """Store today's weighted forecast per close month and tier. Idempotent per (snapshot_date, close_month, tier)."""
    build_views(con, policy)
    as_of = as_of or date.today()
    rows = con.execute("SELECT close_month, account_tier, open_opportunities, open_pipeline, weighted_forecast FROM v_weighted_pipeline").fetchall()
    actuals = {(r[0], r[1]): r[3] for r in con.execute("SELECT close_month, account_tier, won_opportunities, closed_won_actual FROM v_closed_won_by_month").fetchall()}
    con.execute("DELETE FROM forecast_snapshots WHERE snapshot_date = ?", [as_of])
    for close_month, tier, n_open, pipeline, weighted in rows:
        con.execute("INSERT INTO forecast_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [f"FS-{uuid.uuid4().hex[:8].upper()}", as_of, close_month, tier, n_open, pipeline, weighted,
                     actuals.get((close_month, tier), 0), policy.version, correlation_id])
    return len(rows)


def backfill_history(con: duckdb.DuckDBPyConnection, policy: Policy, correlation_id: str, months: int = 6) -> int:
    """Reconstruct what the forecast WOULD have said at the start of each of the last N months, from stage history.

    This is what makes forecast-vs-actual possible on seeded data: for each historical snapshot date we
    rebuild each opportunity's stage as of that date and apply the same stage probabilities.
    """
    sp = _params(policy)
    prob = {"Prospecting": sp["p_prospecting"], "Discovery": sp["p_discovery"], "Proposal": sp["p_proposal"],
            "Negotiation": sp["p_negotiation"]}
    today = date.today().replace(day=1)
    n = 0
    for k in range(months, 0, -1):
        m = today.month - k
        y = today.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        snap = date(y, m, 1)
        rows = con.execute("""
            WITH stage_asof AS (
                SELECT o.opportunity_id, o.amount, o.source_tier, o.close_date, o.created_at,
                       COALESCE((SELECT h.to_stage FROM opportunity_stage_history h
                                 WHERE h.opportunity_id = o.opportunity_id AND h.changed_at < ?
                                 ORDER BY h.changed_at DESC LIMIT 1), 'Prospecting') AS stage_then
                FROM opportunities o WHERE o.created_at < ?
            )
            SELECT DATE_TRUNC('month', close_date)::DATE, source_tier, stage_then, COUNT(*), COALESCE(SUM(amount), 0)
            FROM stage_asof WHERE stage_then NOT IN ('Closed Won', 'Closed Lost')
            GROUP BY 1, 2, 3""", [datetime(snap.year, snap.month, snap.day), snap]).fetchall()
        agg: dict[tuple, list] = {}
        for close_month, tier, stage_then, cnt, amt in rows:
            key = (close_month, tier)
            a = agg.setdefault(key, [0, 0.0, 0.0])
            a[0] += cnt
            a[1] += float(amt)
            a[2] += float(amt) * prob.get(stage_then, 0)
        actuals = {(r[0], r[1]): r[2] for r in con.execute(
            "SELECT DATE_TRUNC('month', close_date)::DATE, source_tier, COALESCE(SUM(amount),0) FROM opportunities WHERE is_won GROUP BY 1,2").fetchall()}
        con.execute("DELETE FROM forecast_snapshots WHERE snapshot_date = ?", [snap])
        for (close_month, tier), (cnt, pipeline, weighted) in agg.items():
            con.execute("INSERT INTO forecast_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [f"FS-{uuid.uuid4().hex[:8].upper()}", snap, close_month, tier, cnt, round(pipeline, 2), round(weighted, 2),
                         actuals.get((close_month, tier), 0), policy.version, correlation_id])
            n += 1
    return n
