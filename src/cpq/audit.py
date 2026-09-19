"""Persist quote evaluations: one quotes row and >= 1 approval_audit rows per decision."""
from __future__ import annotations

import uuid
from datetime import datetime

import duckdb

from src.cpq.evaluate import QuoteEvaluation
from src.policy import Policy


def persist_evaluation(con: duckdb.DuckDBPyConnection, ev: QuoteEvaluation, policy: Policy,
                       correlation_id: str, requested_at: datetime | None = None) -> None:
    now = datetime.now()
    req = ev.request
    quote_id = req.quote_id or f"Q-{uuid.uuid4().hex[:8].upper()}"
    created_at = requested_at or now
    p = ev.priced
    # Preserve a human decision / ERP state from an earlier run: re-evaluating the same request must not undo them.
    prior = con.execute("SELECT approval_status, approver, decision_at, rejection_reason, erp_order_id, erp_status, erp_sent_at "
                        "FROM quotes WHERE quote_id = ?", [quote_id]).fetchone()
    con.execute("DELETE FROM approval_audit WHERE quote_id = ? AND rule_triggered <> 'HUMAN_DECISION'", [quote_id])
    con.execute("DELETE FROM quotes WHERE quote_id = ?", [quote_id])
    con.execute(
        """INSERT INTO quotes (quote_id, account_id, account_name, product_id, monthly_commitment, quantity, contract_term_months,
               discount_percent, payment_terms, custom_pricing, forecasted_units, custom_overage_rate, overage_units, monthly_overage,
               effective_list_price, gross_contract_value, discount_amount, net_contract_value, annual_contract_value,
               approval_status, approval_route, exception_reason, policy_version, sf_quote_id, created_at, evaluated_at, correlation_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            quote_id, req.account_id, req.account_name, req.product_id, req.monthly_commitment, req.quantity,
            req.contract_term_months, req.discount_percent, req.payment_terms, req.has_custom_pricing,
            req.forecasted_units, req.custom_overage_rate,
            p.usage.overage_units if p and p.usage else None,
            p.usage.monthly_overage if p and p.usage else None,
            p.effective_list_price if p else None,
            p.economics.gross_contract_value if p else None,
            p.economics.discount_amount if p else None,
            p.economics.net_contract_value if p else None,
            p.economics.annual_contract_value if p else None,
            ev.decision.status, ev.decision.route, "; ".join(ev.decision.reasons), policy.version,
            None, created_at, now, correlation_id,
        ],
    )
    if prior and prior[0] in ("Approved", "Rejected") and ev.decision.status == "Pending Approval":
        con.execute("UPDATE quotes SET approval_status = ?, approver = ?, decision_at = ?, rejection_reason = ?, "
                    "erp_order_id = ?, erp_status = ?, erp_sent_at = ? WHERE quote_id = ?",
                    [prior[0], prior[1], prior[2], prior[3], prior[4], prior[5], prior[6], quote_id])
    elif prior and prior[4]:
        con.execute("UPDATE quotes SET erp_order_id = ?, erp_status = ?, erp_sent_at = ? WHERE quote_id = ?",
                    [prior[4], prior[5], prior[6], quote_id])
    for i, rule in enumerate(ev.decision.rules, start=1):
        con.execute(
            "INSERT INTO approval_audit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [f"{quote_id}-A{i:02d}", quote_id, rule.rule, req.discount_percent, rule.approver,
             ev.decision.status, rule.reason, now, None, policy.version, correlation_id],
        )
