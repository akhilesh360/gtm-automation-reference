"""Runs the parameterized checks in 04_data_quality_checks.sql and stores results in dq_results."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import duckdb

from src.db import _substitute, read_sql_blocks
from src.policy import Policy

SEVERITY = {
    "accounts_without_domain": "warn",
    "duplicate_account_domains": "error",
    "accounts_without_owner": "error",
    "invalid_discounts": "error",
    "quotes_pending_beyond_sla": "warn",
    "tier1_without_open_task": "error",
    "scores_without_account": "error",
    "signals_without_enrichment": "warn",
    "failed_integration_runs_24h": "warn",
    "approved_quotes_without_erp_order": "warn",
    "erp_orders_not_reconciled": "error",
    "opportunities_without_stage_history": "error",
    "closed_won_missing_amount": "error",
}


@dataclass(frozen=True)
class DqResult:
    check_name: str
    severity: str
    row_count: int
    sample_ids: list[str]


def run_checks(con: duckdb.DuckDBPyConnection, policy: Policy) -> tuple[str, list[DqResult]]:
    blocks = read_sql_blocks("04_data_quality_checks.sql")
    params = {"pending_sla_days": policy.sla.pending_approval_days}
    run_id = f"DQ-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now()
    results: list[DqResult] = []
    for name, sql in blocks.items():
        rows = con.execute(_substitute(sql, params)).fetchall()
        ids = [str(r[0]) for r in rows]
        res = DqResult(name, SEVERITY.get(name, "warn"), len(ids), ids[:5])
        results.append(res)
        con.execute("INSERT INTO dq_results VALUES (?,?,?,?,?,?)",
                    [run_id, name, res.severity, res.row_count, ", ".join(res.sample_ids), now])
    return run_id, results


def has_errors(results: list[DqResult]) -> bool:
    return any(r.severity == "error" and r.row_count > 0 for r in results)
