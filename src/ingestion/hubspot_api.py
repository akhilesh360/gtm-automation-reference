"""HubSpot CRM API adapter (v2). Pulls email and meeting engagements with a private-app token and writes the same
CSV shape the offline path reads (data/raw/hubspot_engagement.csv), so load_hubspot.py needs no changes.

Endpoints: /crm/v3/objects/emails and /crm/v3/objects/meetings (search by hs_timestamp), each with contact
associations, then /crm/v3/objects/contacts batch read for the contact email. Keep it small; a production adapter
would page fully and handle rate limits.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from src.config import settings

BASE = "https://api.hubapi.com"


def _search(client: httpx.Client, obj: str, since_ms: int, props: list[str]) -> list[dict[str, Any]]:
    body = {"filterGroups": [{"filters": [{"propertyName": "hs_timestamp", "operator": "GTE", "value": str(since_ms)}]}],
            "properties": props, "limit": 100}
    r = client.post(f"{BASE}/crm/v3/objects/{obj}/search", json=body)
    r.raise_for_status()
    return r.json().get("results", [])


def _contact_emails(client: httpx.Client, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    r = client.post(f"{BASE}/crm/v3/objects/contacts/batch/read", json={"properties": ["email"], "inputs": [{"id": i} for i in ids[:100]]})
    r.raise_for_status()
    return {c["id"]: (c.get("properties") or {}).get("email") or "" for c in r.json().get("results", [])}


def _associated_contact(client: httpx.Client, obj: str, obj_id: str) -> str | None:
    r = client.get(f"{BASE}/crm/v4/objects/{obj}/{obj_id}/associations/contacts")
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return str(results[0]["toObjectId"]) if results else None


def pull_engagements(out_path: Path, token: str | None = None, lookback_days: int | None = None, client: httpx.Client | None = None) -> int:
    token = token or settings.hubspot_token
    lookback_days = lookback_days or settings.hubspot_lookback_days
    since_ms = int((datetime.now() - timedelta(days=lookback_days)).timestamp() * 1000)
    own = client is None
    client = client or httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
    rows: list[list[Any]] = []
    try:
        for obj, props, kind in (("emails", ["hs_timestamp", "hs_email_subject", "hs_email_status", "hs_email_direction"], "email"),
                                 ("meetings", ["hs_timestamp", "hs_meeting_title"], "meeting")):
            for item in _search(client, obj, since_ms, props):
                pr = item.get("properties") or {}
                contact_id = _associated_contact(client, obj, item["id"])
                email = _contact_emails(client, [contact_id]).get(contact_id, "") if contact_id else ""
                domain = email.split("@")[-1].lower() if "@" in email else ""
                ts = (pr.get("hs_timestamp") or "")[:19].replace("T", " ")
                if kind == "meeting":
                    etype, campaign = "meeting_booked", pr.get("hs_meeting_title") or "Meeting"
                else:
                    direction = (pr.get("hs_email_direction") or "").upper()
                    etype = "email_click" if "CLICK" in (pr.get("hs_email_status") or "").upper() else "email_open"
                    if direction == "INCOMING_EMAIL":
                        etype = "email_click"  # a reply is the strongest email engagement we model
                    campaign = pr.get("hs_email_subject") or "Email"
                rows.append([f"HS-API-{item['id']}", email, domain, etype, ts, campaign])
    finally:
        if own:
            client.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["event_id", "contact_email", "domain", "event_type", "event_timestamp", "campaign"])
        w.writerows(rows)
    return len(rows)
