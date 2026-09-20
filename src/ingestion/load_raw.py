"""Load raw CSVs into DuckDB via 02_load_raw_data.sql, then normalize HubSpot events into intent_signals."""
from __future__ import annotations

import duckdb

from src.config import settings
from src.db import run_sql_file
from src.ingestion.load_hubspot import load_hubspot_events


def load_all(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    live_path = settings.processed_dir / "hubspot_engagement_live.csv"   # git-ignored; the seeded export stays untouched
    if settings.hubspot_enabled and settings.hubspot_token:
        from src.ingestion.hubspot_api import pull_engagements  # live pull is loaded IN ADDITION to the CSV export

        pull_engagements(live_path)
    run_sql_file(con, "02_load_raw_data.sql", {"raw_dir": str(settings.raw_dir)})
    extra = settings.processed_dir / "accounts_live.csv"   # optional, git-ignored: real accounts used for live connector tests
    if extra.exists():
        con.execute("INSERT OR REPLACE INTO accounts (account_id, account_name, domain, industry, employee_count, funding_stage, account_owner, "
                    "created_at, updated_at) SELECT account_id, account_name, domain, industry, employee_count, funding_stage, account_owner, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM read_csv_auto(?, header=true)", [str(extra)])
    hubspot_rows = load_hubspot_events(con, [settings.raw_dir / "hubspot_engagement.csv", live_path])
    counts = {}
    for t in ("accounts", "account_enrichment", "intent_signals", "usage_signals", "products", "quote_requests", "opportunities", "opportunity_stage_history"):
        counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    counts["hubspot_signals"] = hubspot_rows
    return counts
