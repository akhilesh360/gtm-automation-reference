"""Standalone HTTP mock of a NetSuite-style sales-order API. Run: uvicorn erp.mock_server:app --port 8100

Set ERP_URL=http://127.0.0.1:8100 to make the engine hand off over HTTP instead of in-process.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.erp.netsuite_mock import ErpError, MockNetSuiteClient  # noqa: E402

app = FastAPI(title="Mock NetSuite sales-order API", version="0.1.0")
_store = MockNetSuiteClient()


@app.post("/sales-orders", status_code=201)
def create_sales_order(payload: dict) -> dict:
    try:
        return _store.create_sales_order(payload)
    except ErpError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/sales-orders/{sales_order_id}")
def get_sales_order(sales_order_id: str) -> dict:
    order = _store.get_sales_order(sales_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="not found")
    return order


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "orders": len(_store._orders)}
