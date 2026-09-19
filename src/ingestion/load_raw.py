"""Load raw CSVs into DuckDB via 02_load_raw_data.sql, then normalize HubSpot events into intent_signals."""
from __future__ import annotations

import duckdb

from src.config import settings
from src.db import run_sql_file
from src.ingestion.load_hubspot import load_hubspot_events


def load_all(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    run_sql_file(con, "02_load_raw_data.sql", {"raw_dir": str(settings.raw_dir)})
    hubspot_rows = load_hubspot_events(con, settings.raw_dir / "hubspot_engagement.csv")
    counts = {}
    for t in ("accounts", "account_enrichment", "intent_signals", "usage_signals", "products", "quote_requests", "opportunities", "opportunity_stage_history"):
        counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    counts["hubspot_signals"] = hubspot_rows
    return counts
