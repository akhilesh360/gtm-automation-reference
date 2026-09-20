"""Read-only tools the research agent may call. Each one is a plain function over DuckDB; the schemas describe them
to the model. Nothing here writes, and nothing here can change a score, tier, price or approval."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import duckdb


def get_account(con: duckdb.DuckDBPyConnection, account_id: str) -> dict[str, Any]:
    r = con.execute("""SELECT a.account_name, a.domain, a.industry, a.employee_count, a.funding_stage, a.account_owner,
                              s.account_tier, s.priority_score, s.scoring_reason, s.intent_score, s.usage_score, s.engagement_score, s.firmographic_fit_score
                       FROM accounts a LEFT JOIN account_scores s ON s.account_id = a.account_id WHERE a.account_id = ?""", [account_id]).fetchone()
    if not r:
        return {"error": "account not found"}
    keys = ["account_name", "domain", "industry", "employee_count", "funding_stage", "account_owner", "account_tier", "priority_score",
            "scoring_reason", "intent_score", "usage_score", "engagement_score", "firmographic_fit_score"]
    return {k: (float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, int) else v) for k, v in zip(keys, r)}


def get_enrichment(con: duckdb.DuckDBPyConnection, account_id: str) -> dict[str, Any]:
    r = con.execute("""SELECT employee_count, funding_stage, funding_amount_usd, tech_stack, open_ml_roles, open_data_infra_roles,
                              company_summary, personalization_hook, enrichment_source FROM account_enrichment WHERE account_id = ?""", [account_id]).fetchone()
    if not r:
        return {"error": "no enrichment row"}
    keys = ["employee_count", "funding_stage", "funding_amount_usd", "tech_stack", "open_ml_roles", "open_data_infra_roles",
            "company_summary", "personalization_hook", "enrichment_source"]
    return {k: (float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, int) else v) for k, v in zip(keys, r)}


def get_signals(con: duckdb.DuckDBPyConnection, account_id: str, days: int = 90) -> dict[str, Any]:
    rows = con.execute("""SELECT signal_type, signal_source, SUM(signal_value), MAX(signal_timestamp) FROM intent_signals
                          WHERE account_id = ? AND signal_timestamp >= CURRENT_TIMESTAMP - INTERVAL (?) DAY
                          GROUP BY 1, 2 ORDER BY 3 DESC""", [account_id, int(days)]).fetchall()
    usage = con.execute("SELECT month, api_calls, active_users, mom_growth_pct FROM usage_signals WHERE account_id = ? ORDER BY month DESC LIMIT 3", [account_id]).fetchall()
    return {"signals": [{"type": r[0], "source": r[1], "total": float(r[2]), "last_seen": str(r[3])} for r in rows],
            "usage_last_3_months": [{"month": str(u[0]), "api_calls": int(u[1]), "active_users": int(u[2]), "mom_growth_pct": float(u[3])} for u in usage]}


def get_open_quotes(con: duckdb.DuckDBPyConnection, account_id: str) -> dict[str, Any]:
    rows = con.execute("""SELECT quote_id, product_id, monthly_commitment, discount_percent, payment_terms, annual_contract_value, approval_status, approval_route
                          FROM quotes WHERE account_id = ? ORDER BY created_at DESC""", [account_id]).fetchall()
    return {"quotes": [{"quote_id": r[0], "product_id": r[1], "monthly_commitment": float(r[2] or 0), "discount_percent": float(r[3] or 0),
                        "payment_terms": r[4], "acv": float(r[5] or 0), "status": r[6], "route": r[7]} for r in rows]}


def get_opportunities(con: duckdb.DuckDBPyConnection, account_id: str) -> dict[str, Any]:
    rows = con.execute("SELECT opportunity_id, name, amount, stage, close_date, is_closed, is_won FROM opportunities WHERE account_id = ? ORDER BY created_at DESC", [account_id]).fetchall()
    return {"opportunities": [{"id": r[0], "name": r[1], "amount": float(r[2] or 0), "stage": r[3], "close_date": str(r[4]),
                               "is_closed": bool(r[5]), "is_won": bool(r[6])} for r in rows]}


TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_account": get_account, "get_enrichment": get_enrichment, "get_signals": get_signals,
    "get_open_quotes": get_open_quotes, "get_opportunities": get_opportunities,
}

_ID = {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"], "additionalProperties": False}
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "get_account", "description": "Firmographics, owner, tier, priority score and the deterministic scoring reason.", "input_schema": _ID, "strict": True},
    {"name": "get_enrichment", "description": "Clay-shaped enrichment: funding, headcount, tech stack, open ML and data-infra roles, company summary, personalization hook.", "input_schema": _ID, "strict": True},
    {"name": "get_signals", "description": "Intent and engagement signals in a window (default 90 days) and the last three months of product usage.",
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}, "days": {"type": "integer", "minimum": 1, "maximum": 365}},
                      "required": ["account_id", "days"], "additionalProperties": False}, "strict": True},
    {"name": "get_open_quotes", "description": "Quotes for the account with pricing, discount, terms, ACV and approval status.", "input_schema": _ID, "strict": True},
    {"name": "get_opportunities", "description": "Opportunities for the account with amount, stage and outcome.", "input_schema": _ID, "strict": True},
]


def run_tool(con: duckdb.DuckDBPyConnection, name: str, args: dict[str, Any]) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(con, **args), default=str)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)})
