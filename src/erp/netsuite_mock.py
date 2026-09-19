"""NetSuite-style mock ERP. Same interface in-process (default) or over HTTP (ERP_URL set).

A real NetSuite REST adapter replaces MockNetSuiteClient; everything upstream stays the same.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from src.config import settings


class ErpError(ValueError):
    """Payload rejected by the ERP (validation), never retried."""


class ErpClient(Protocol):
    name: str

    def create_sales_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_sales_order(self, sales_order_id: str) -> dict[str, Any] | None: ...


REQUIRED = ("external_quote_id", "customer", "terms", "lines", "totals", "billing_schedule")


def validate_payload(payload: dict[str, Any]) -> None:
    missing = [k for k in REQUIRED if k not in payload or payload[k] in (None, [], {})]
    if missing:
        raise ErpError(f"missing required fields: {missing}")
    if not payload["customer"].get("name"):
        raise ErpError("customer.name is required")
    if payload["terms"].get("contract_term_months", 0) <= 0:
        raise ErpError("terms.contract_term_months must be positive")
    net = round(float(payload["totals"]["net"]), 2)
    if net <= 0:
        raise ErpError("totals.net must be positive")
    sched = round(sum(float(l["amount"]) for l in payload["billing_schedule"]), 2)
    if abs(sched - net) > 0.01:
        raise ErpError(f"billing schedule sums to {sched}, expected {net}")
    lines = round(sum(float(l["amount"]) for l in payload["lines"]), 2)
    if abs(lines - net) > 0.01:
        raise ErpError(f"line amounts sum to {lines}, expected {net}")


class MockNetSuiteClient:
    name = "mock-netsuite"

    def __init__(self, path: Path | None = None):
        self.path = path or settings.mock_erp_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._orders: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            try:
                self._orders = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._orders = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._orders, indent=2, default=str), encoding="utf-8")

    def create_sales_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_payload(payload)
        ext = payload["external_quote_id"]
        existing = next((o for o in self._orders.values() if o["external_quote_id"] == ext), None)
        if existing:  # idempotent: the same quote always maps to the same order
            return {"sales_order_id": existing["sales_order_id"], "status": existing["status"],
                    "accepted_total": existing["accepted_total"], "duplicate": True}
        so_id = "SO-" + hashlib.sha1(ext.encode()).hexdigest()[:8].upper()
        order = {"sales_order_id": so_id, "external_quote_id": ext, "status": "Pending Fulfillment",
                 "accepted_total": round(float(payload["totals"]["net"]), 2),
                 "customer": payload["customer"]["name"], "created_at": datetime.now().isoformat(timespec="seconds"),
                 "payload": payload}
        self._orders[so_id] = order
        self._save()
        return {"sales_order_id": so_id, "status": order["status"], "accepted_total": order["accepted_total"], "duplicate": False}

    def get_sales_order(self, sales_order_id: str) -> dict[str, Any] | None:
        return self._orders.get(sales_order_id)


class HttpNetSuiteClient:
    """Same contract over HTTP, against erp/mock_server.py or a real adapter behind ERP_URL."""
    name = "http-erp"

    def __init__(self, base_url: str):
        import httpx
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(timeout=15.0)

    def create_sales_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.http.post(f"{self.base}/sales-orders", json=payload)
        if r.status_code == 422:
            raise ErpError(r.json().get("detail", "rejected"))
        r.raise_for_status()
        return r.json()

    def get_sales_order(self, sales_order_id: str) -> dict[str, Any] | None:
        r = self.http.get(f"{self.base}/sales-orders/{sales_order_id}")
        return r.json() if r.status_code == 200 else None


def get_erp_client() -> ErpClient:
    if settings.erp_url:
        return HttpNetSuiteClient(settings.erp_url)
    return MockNetSuiteClient()
