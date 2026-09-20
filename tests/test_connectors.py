"""v2 item 5: Clay webhook and HubSpot API adapters, tested offline."""
import csv

import duckdb
import httpx
from fastapi.testclient import TestClient

from src.ingestion.clay_webhook import ingest_clay_rows, normalize_row
from src.ingestion.hubspot_api import pull_engagements


def test_normalize_accepts_clay_aliases():
    n = normalize_row({"Website": "https://www.FastScale.ai/about", "Headcount": "3200", "Last Funding Round": "Series B",
                       "Technologies": ["Python", "PyTorch"], "Open ML Roles": 2, "Personalization Hook": "your inference push"})
    assert n["domain"] == "fastscale.ai" and n["employee_count"] == 3200 and n["tech_stack"] == "python,pytorch"
    assert n["open_ml_roles"] == 2 and n["funding_stage"] == "Series B"


def test_normalize_rejects_rows_without_domain():
    assert normalize_row({"Headcount": 10}) is None


def test_ingest_matches_by_domain_and_adds_signal(pipeline_db):
    con = duckdb.connect(str(pipeline_db))
    res = ingest_clay_rows(con, [{"domain": "fastscale.ai", "headcount": 3300, "open_ml_roles": 4, "hook": "new hook"},
                                 {"domain": "nobody.example", "headcount": 5}, {"headcount": 1}], "run-t")
    assert res["upserted"] == 1 and res["unmatched_domains"] == ["nobody.example"] and res["invalid"] == 1
    r = con.execute("SELECT employee_count, personalization_hook, enrichment_source FROM account_enrichment WHERE account_id = 'ACC-00003'").fetchone()
    assert r == (3300, "new hook", "clay_webhook")
    assert con.execute("SELECT COUNT(*) FROM intent_signals WHERE account_id = 'ACC-00003' AND signal_source = 'clay_webhook'").fetchone()[0] == 1
    con.close()


def test_webhook_route_absent_by_default():
    from api.app import app
    assert not any(getattr(r, "path", "") == "/webhooks/clay" for r in app.routes)


def test_webhook_route_present_and_secured_when_enabled(monkeypatch, pipeline_db):
    from src import config
    monkeypatch.setattr(config.settings, "clay_enabled", True)
    monkeypatch.setattr(config.settings, "clay_webhook_secret", "s3cret")
    from fastapi import FastAPI

    from api.routes import clay_webhook
    app = FastAPI()
    app.include_router(clay_webhook.router)
    c = TestClient(app)
    assert c.post("/webhooks/clay", json=[{"domain": "fastscale.ai"}]).status_code == 401
    r = c.post("/webhooks/clay", json=[{"domain": "fastscale.ai", "headcount": 3400}], headers={"X-Clay-Secret": "s3cret"})
    assert r.status_code == 202 and r.json()["upserted"] == 1


def test_hubspot_pull_writes_csv_shape(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/objects/emails/search"):
            return httpx.Response(200, json={"results": [{"id": "e1", "properties": {"hs_timestamp": "2026-09-10T10:00:00Z", "hs_email_subject": "Pricing", "hs_email_status": "SENT", "hs_email_direction": "INCOMING_EMAIL"}}]})
        if p.endswith("/objects/meetings/search"):
            return httpx.Response(200, json={"results": [{"id": "m1", "properties": {"hs_timestamp": "2026-09-12T15:00:00Z", "hs_meeting_title": "Demo"}}]})
        if "/associations/contacts" in p:
            return httpx.Response(200, json={"results": [{"toObjectId": 42}]})
        if p.endswith("/contacts/batch/read"):
            return httpx.Response(200, json={"results": [{"id": "42", "properties": {"email": "cto@fastscale.ai"}}]})
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = tmp_path / "hubspot_engagement.csv"
    n = pull_engagements(out, token="t", lookback_days=30, client=client)
    rows = list(csv.DictReader(open(out)))
    assert n == 2 and {r["event_type"] for r in rows} == {"email_click", "meeting_booked"}
    assert all(r["domain"] == "fastscale.ai" for r in rows)
