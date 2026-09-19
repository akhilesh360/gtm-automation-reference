"""HubSpot adapter (v1: CSV export). Maps engagement events into intent_signals with signal_source = 'hubspot'.

Mapping:
  email_open / email_click        -> email_engagement (1)
  form_submit "Contact sales"     -> demo_request (1); other forms -> website_visit (1)
  page_view on /pricing           -> pricing_page_visit (1); other page views -> website_visit (1)
  meeting_booked                  -> demo_request (1)
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def map_event(event_type: str, campaign: str | None) -> str | None:
    c = (campaign or "").lower()
    if event_type in ("email_open", "email_click"):
        return "email_engagement"
    if event_type == "meeting_booked":
        return "demo_request"
    if event_type == "form_submit":
        return "demo_request" if "contact sales" in c else "website_visit"
    if event_type == "page_view":
        return "pricing_page_visit" if "pricing" in c else "website_visit"
    return None


def load_hubspot_events(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    if not path.exists():
        return 0
    df = pd.read_csv(path)
    domains = con.execute("SELECT domain, account_id FROM accounts WHERE domain IS NOT NULL").fetchall()
    by_domain = {d: a for d, a in domains}
    rows = []
    for r in df.itertuples(index=False):
        aid = by_domain.get(r.domain)
        stype = map_event(r.event_type, getattr(r, "campaign", None))
        if aid is None or stype is None:
            continue
        rows.append((f"HS-{r.event_id}", aid, stype, 1.0, "hubspot", r.event_timestamp))
    con.execute("DELETE FROM intent_signals WHERE signal_source = 'hubspot'")
    if rows:
        con.executemany("INSERT INTO intent_signals VALUES (?,?,?,?,?,?)", rows)
    return len(rows)
