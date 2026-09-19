"""Schema validation of raw CSVs before they are loaded. Returns a list of issues; empty means clean."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED: dict[str, list[str]] = {
    "accounts.csv": ["account_id", "account_name", "domain", "industry", "employee_count", "funding_stage", "account_owner"],
    "clay_enrichment.csv": ["enrichment_id", "account_id", "domain", "employee_count", "funding_stage", "open_ml_roles", "enrichment_source"],
    "intent_signals.csv": ["signal_id", "account_id", "signal_type", "signal_value", "signal_source", "signal_timestamp"],
    "hubspot_engagement.csv": ["event_id", "contact_email", "domain", "event_type", "event_timestamp"],
    "usage_signals.csv": ["usage_id", "account_id", "month", "api_calls", "active_users", "mom_growth_pct"],
    "products.csv": ["product_id", "product_name", "pricing_model", "list_price_monthly"],
    "opportunities.csv": ["opportunity_id", "account_id", "name", "amount", "stage", "created_at", "close_date", "is_closed", "is_won", "source_tier"],
    "opportunity_stage_history.csv": ["history_id", "opportunity_id", "from_stage", "to_stage", "changed_at", "days_in_from_stage"],
    "quote_requests.csv": ["quote_id", "account_id", "account_name", "product_id", "monthly_commitment", "quantity",
                           "contract_term_months", "discount_percent", "payment_terms", "custom_pricing"],
}
SIGNAL_TYPES = {"website_visit", "pricing_page_visit", "demo_request", "job_posting_ml_engineer", "funding_event",
                "product_usage_growth", "email_engagement", "open_source_model_interest"}
HUBSPOT_EVENTS = {"email_open", "email_click", "form_submit", "page_view", "meeting_booked"}


@dataclass(frozen=True)
class SchemaIssue:
    file: str
    severity: str  # error | warn
    message: str


def validate_raw_dir(raw_dir: Path) -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    frames: dict[str, pd.DataFrame] = {}
    for fname, cols in REQUIRED.items():
        path = raw_dir / fname
        if not path.exists():
            issues.append(SchemaIssue(fname, "error", "file missing"))
            continue
        df = pd.read_csv(path)
        frames[fname] = df
        missing = [c for c in cols if c not in df.columns]
        if missing:
            issues.append(SchemaIssue(fname, "error", f"missing columns: {missing}"))
        key = cols[0]
        if key in df.columns and df[key].duplicated().any():
            issues.append(SchemaIssue(fname, "error", f"duplicate {key} values"))

    acc = frames.get("accounts.csv")
    if acc is not None:
        ids = set(acc["account_id"])
        for fname in ("intent_signals.csv", "usage_signals.csv", "quote_requests.csv", "clay_enrichment.csv", "opportunities.csv"):
            df = frames.get(fname)
            if df is not None and "account_id" in df.columns:
                orphans = set(df["account_id"]) - ids
                if orphans:
                    issues.append(SchemaIssue(fname, "error", f"{len(orphans)} rows reference unknown account_id"))
    sig = frames.get("intent_signals.csv")
    if sig is not None and "signal_type" in sig.columns:
        bad = set(sig["signal_type"]) - SIGNAL_TYPES
        if bad:
            issues.append(SchemaIssue("intent_signals.csv", "error", f"unknown signal_type values: {sorted(bad)}"))
    hs = frames.get("hubspot_engagement.csv")
    if hs is not None and "event_type" in hs.columns:
        bad = set(hs["event_type"]) - HUBSPOT_EVENTS
        if bad:
            issues.append(SchemaIssue("hubspot_engagement.csv", "error", f"unknown event_type values: {sorted(bad)}"))
    q = frames.get("quote_requests.csv")
    if q is not None and "discount_percent" in q.columns:
        n = int(((q["discount_percent"] < 0) | (q["discount_percent"] > 100)).sum())
        if n:
            issues.append(SchemaIssue("quote_requests.csv", "warn", f"{n} rows with discount outside 0-100 (will fail validation, not load)"))
    return issues
