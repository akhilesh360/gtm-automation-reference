"""Build the sales-order payload handed to the ERP. Pure function of a quotes row + account."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

PREPAID_TERMS = {"Annual Prepaid"}


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def billing_schedule(net_total: float, term_months: int, payment_terms: str, start: date) -> list[dict[str, Any]]:
    """Monthly lines for Net terms; one up-front line for prepaid. The lines always sum exactly to net_total."""
    if payment_terms in PREPAID_TERMS or term_months <= 1:
        return [{"period": 1, "due_date": start.isoformat(), "amount": round(net_total, 2)}]
    per = round(net_total / term_months, 2)
    lines = [{"period": i + 1, "due_date": _add_months(start, i).isoformat(), "amount": per} for i in range(term_months)]
    lines[-1]["amount"] = round(net_total - per * (term_months - 1), 2)  # absorb rounding in the last line
    return lines


def build_sales_order(q: dict[str, Any], account: dict[str, Any], product: dict[str, Any] | None,
                      policy_version: str, correlation_id: str, start: date | None = None) -> dict[str, Any]:
    start = start or (date.today().replace(day=1) + timedelta(days=32)).replace(day=1)  # first of next month
    term = int(q["contract_term_months"])
    net = float(q["net_contract_value"])
    net_monthly = round(net / term, 2)
    line = {
        "product_id": q["product_id"],
        "description": (product or {}).get("product_name", q["product_id"]),
        "quantity": int(q["quantity"] or 1),
        "monthly_rate": float(q["effective_list_price"]),
        "discount_percent": float(q["discount_percent"]),
        "net_monthly_rate": net_monthly,
        "term_months": term,
        "amount": round(net, 2),
    }
    usage = None
    if product and product.get("pricing_model") == "usage":
        usage = {
            "included_units": int(product.get("included_units") or 0),
            "forecasted_units": int(q["forecasted_units"] or 0),
            "overage_rate": float(q["custom_overage_rate"]) if q.get("custom_overage_rate") is not None else float(product.get("overage_price_per_unit") or 0),
            "custom_overage": q.get("custom_overage_rate") is not None,
        }
    return {
        "external_quote_id": q["quote_id"],
        "policy_version": policy_version,
        "correlation_id": correlation_id,
        "customer": {"name": q["account_name"], "external_account_id": q["account_id"],
                     "salesforce_account_id": account.get("sf_account_id")},
        "terms": {"contract_term_months": term, "payment_terms": q["payment_terms"], "start_date": start.isoformat()},
        "lines": [line],
        "usage": usage,
        "totals": {"gross": float(q["gross_contract_value"]), "discount": float(q["discount_amount"]),
                   "net": round(net, 2), "annual_contract_value": float(q["annual_contract_value"])},
        "billing_schedule": billing_schedule(net, term, q["payment_terms"], start),
    }
