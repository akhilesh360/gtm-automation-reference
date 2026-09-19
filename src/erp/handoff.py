"""ERP handoff stage: approved quotes -> sales order -> reconciliation -> write-back."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import duckdb

from src.erp.netsuite_mock import ErpClient, ErpError
from src.erp.payload import build_sales_order
from src.monitoring.logger import STATUS_FAILED_API, STATUS_FAILED_VALIDATION, STATUS_RECONCILED, get_logger, write_integration_log
from src.policy import get_policy

log = get_logger()
ELIGIBLE = ("Auto-Approved", "Approved")


def handoff_approved_quotes(con: duckdb.DuckDBPyConnection, erp: ErpClient, correlation_id: str) -> dict[str, int]:
    policy = get_policy()
    cols = [d[0] for d in con.execute("SELECT * FROM quotes LIMIT 0").description]
    rows = con.execute(
        f"SELECT * FROM quotes WHERE approval_status IN {ELIGIBLE} AND (erp_status IS NULL OR erp_status IN ('Not Sent', 'Failed'))"
    ).fetchall()
    products = {r[0]: {"product_id": r[0], "product_name": r[1], "pricing_model": r[2], "list_price_monthly": r[3],
                       "included_units": r[4], "overage_price_per_unit": r[5]} for r in con.execute("SELECT * FROM products").fetchall()}
    counts = {"sent": 0, "reconciled": 0, "failed": 0, "duplicate": 0}
    for r in rows:
        q = dict(zip(cols, r))
        acct = con.execute("SELECT account_id, sf_account_id FROM accounts WHERE account_id = ?", [q["account_id"]]).fetchone()
        account = {"account_id": acct[0], "sf_account_id": acct[1]} if acct else {}
        payload = build_sales_order(q, account, products.get(q["product_id"]), policy.version, correlation_id)
        now = datetime.now()
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        try:
            resp = erp.create_sales_order(payload)
        except ErpError as e:
            con.execute("INSERT INTO erp_orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [order_id, q["quote_id"], None, "FAILED_VALIDATION", json.dumps(payload), None, now, None, str(e), correlation_id])
            con.execute("UPDATE quotes SET erp_status = 'Failed', erp_sent_at = ? WHERE quote_id = ?", [now, q["quote_id"]])
            write_integration_log(con, "erp_handoff", STATUS_FAILED_VALIDATION, correlation_id, "quote", q["quote_id"], error=str(e))
            counts["failed"] += 1
            continue
        except Exception as e:  # noqa: BLE001  network / 5xx
            write_integration_log(con, "erp_handoff", STATUS_FAILED_API, correlation_id, "quote", q["quote_id"], error=str(e))
            counts["failed"] += 1
            continue
        counts["sent"] += 1
        if resp.get("duplicate"):
            counts["duplicate"] += 1
        accepted = float(resp["accepted_total"])
        expected = round(float(q["net_contract_value"]), 2)
        if abs(accepted - expected) <= 0.01:
            status, erp_status, err = "RECONCILED", "Reconciled", None
            counts["reconciled"] += 1
            write_integration_log(con, "erp_handoff", STATUS_RECONCILED, correlation_id, "quote", q["quote_id"])
        else:
            status, erp_status = "FAILED_RECONCILIATION", "Failed"
            err = f"ERP accepted {accepted:,.2f} but quote net is {expected:,.2f}"
            counts["failed"] += 1
            write_integration_log(con, "erp_handoff", STATUS_FAILED_API, correlation_id, "quote", q["quote_id"], error=err)
        con.execute("DELETE FROM erp_orders WHERE quote_id = ?", [q["quote_id"]])
        con.execute("INSERT INTO erp_orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [order_id, q["quote_id"], resp["sales_order_id"], status, json.dumps(payload), accepted, now,
                     now if status == "RECONCILED" else None, err, correlation_id])
        con.execute("UPDATE quotes SET erp_order_id = ?, erp_status = ?, erp_sent_at = ? WHERE quote_id = ?",
                    [resp["sales_order_id"], erp_status, now, q["quote_id"]])
        log.info("erp handoff", extra={"workflow": "erp_handoff", "record_id": q["quote_id"], "status": status,
                                        "correlation_id": correlation_id, "extra": {"sales_order_id": resp["sales_order_id"]}})
    return counts
