"""Clay webhook adapter (v2). Normalizes a Clay "Send to HTTP API" payload into account_enrichment rows.

Clay tables are user-defined, so column names vary. The mapper accepts the common aliases below and ignores
anything else. Rows are matched to accounts by domain; unmatched rows are reported, not stored.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import duckdb

ALIASES: dict[str, tuple[str, ...]] = {
    "domain": ("domain", "website", "company_domain", "Domain", "Website"),
    "employee_count": ("employee_count", "headcount", "employees", "Employee Count", "Headcount", "Employees"),
    "funding_stage": ("funding_stage", "last_funding_round", "funding_round", "Funding Stage", "Last Funding Round", "Type"),
    "funding_amount_usd": ("funding_amount_usd", "total_funding", "funding_amount", "Total Funding"),
    "tech_stack": ("tech_stack", "technologies", "tech", "Tech Stack", "Technologies"),
    "open_ml_roles": ("open_ml_roles", "ml_job_postings", "ml_roles", "Open ML Roles"),
    "open_data_infra_roles": ("open_data_infra_roles", "data_infra_roles", "Data Infra Roles"),
    "company_summary": ("company_summary", "summary", "description", "Description", "Company Summary", "About"),
    "personalization_hook": ("personalization_hook", "hook", "icebreaker", "Personalization Hook"),
}


def _pick(row: dict[str, Any], key: str) -> Any:
    for alias in ALIASES[key]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    domain = _pick(row, "domain")
    if not domain:
        return None
    domain = str(domain).lower().replace("https://", "").replace("http://", "").split("/")[0].removeprefix("www.")
    stack = _pick(row, "tech_stack")
    if isinstance(stack, list):
        stack = ",".join(str(x).strip().lower() for x in stack)

    def as_int(v):
        try:
            return int(float(v)) if v is not None else None
        except (TypeError, ValueError):
            return None
    return {
        "domain": domain,
        "employee_count": as_int(_pick(row, "employee_count")),
        "funding_stage": _pick(row, "funding_stage"),
        "funding_amount_usd": as_int(_pick(row, "funding_amount_usd")),
        "tech_stack": stack,
        "open_ml_roles": as_int(_pick(row, "open_ml_roles")) or 0,
        "open_data_infra_roles": as_int(_pick(row, "open_data_infra_roles")) or 0,
        "company_summary": _pick(row, "company_summary"),
        "personalization_hook": _pick(row, "personalization_hook"),
    }


def ingest_clay_rows(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]], correlation_id: str) -> dict[str, Any]:
    by_domain = {d: a for d, a in con.execute("SELECT domain, account_id FROM accounts WHERE domain IS NOT NULL").fetchall()}
    now = datetime.now()
    upserted, unmatched, invalid = 0, [], 0
    for raw in rows:
        n = normalize_row(raw)
        if n is None:
            invalid += 1
            continue
        aid = by_domain.get(n["domain"])
        if not aid:
            unmatched.append(n["domain"])
            continue
        con.execute("DELETE FROM account_enrichment WHERE account_id = ?", [aid])
        con.execute("INSERT INTO account_enrichment VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [f"ENR-W-{uuid.uuid4().hex[:8].upper()}", aid, n["domain"], n["employee_count"], n["funding_stage"],
                     n["funding_amount_usd"], n["tech_stack"], n["open_ml_roles"], n["open_data_infra_roles"],
                     n["company_summary"], n["personalization_hook"], "clay_webhook", now])
        if n["open_ml_roles"]:
            con.execute("DELETE FROM intent_signals WHERE account_id = ? AND signal_type = 'job_posting_ml_engineer' AND signal_source = 'clay_webhook'", [aid])
            con.execute("INSERT INTO intent_signals VALUES (?,?,?,?,?,?)",
                        [f"SIG-W-{uuid.uuid4().hex[:8].upper()}", aid, "job_posting_ml_engineer", float(n["open_ml_roles"]), "clay_webhook", now])
        upserted += 1
    return {"received": len(rows), "upserted": upserted, "unmatched_domains": unmatched, "invalid": invalid, "correlation_id": correlation_id}
