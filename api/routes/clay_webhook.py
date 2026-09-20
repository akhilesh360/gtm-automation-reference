"""POST /webhooks/clay — registered only when CLAY_ENABLED=true. Clay's "Send to HTTP API" action posts here."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from src.config import settings
from src.db import session
from src.ingestion.clay_webhook import ingest_clay_rows
from src.monitoring.logger import STATUS_SUCCESS, new_correlation_id, write_integration_log

router = APIRouter()


@router.post("/webhooks/clay", status_code=202, tags=["connectors"])
def clay_webhook(payload: dict[str, Any] | list[dict[str, Any]], x_clay_secret: str | None = Header(default=None)) -> dict[str, Any]:
    if settings.clay_webhook_secret and x_clay_secret != settings.clay_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")
    rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("data") or [payload]
    cid = new_correlation_id()
    with session() as con:
        result = ingest_clay_rows(con, rows, cid)
        write_integration_log(con, "clay_webhook", STATUS_SUCCESS, cid, "account_enrichment", None)
    return result
