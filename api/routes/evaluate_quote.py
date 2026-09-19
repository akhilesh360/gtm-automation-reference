from fastapi import APIRouter

from api.models import ApprovalOut, AuditRowOut, EvaluateQuoteRequest, EvaluateQuoteResponse
from src.cpq.evaluate import evaluate_quote
from src.cpq.models import Product, QuoteRequest
from src.db import session
from src.policy import get_policy

router = APIRouter()


def _load_product(product_id: str) -> Product | None:
    with session() as con:
        r = con.execute("SELECT * FROM products WHERE product_id = ?", [product_id]).fetchone()
    if not r:
        return None
    return Product(product_id=r[0], product_name=r[1], pricing_model=r[2], list_price_monthly=float(r[3]),
                   included_units=int(r[4]) if r[4] is not None else None,
                   overage_price_per_unit=float(r[5]) if r[5] is not None else None)


@router.post("/evaluate-quote", response_model=EvaluateQuoteResponse, tags=["business"])
def evaluate(req: EvaluateQuoteRequest) -> EvaluateQuoteResponse:
    policy = get_policy()
    product = _load_product(req.product_id)
    ev = evaluate_quote(QuoteRequest(**req.model_dump()), product, policy)
    p = ev.priced
    return EvaluateQuoteResponse(
        economics=p.economics.__dict__ if p else None,
        usage={k: float(v) for k, v in p.usage.__dict__.items()} if p and p.usage else None,
        approval=ApprovalOut(status=ev.decision.status, approvers=ev.decision.approvers, reasons=ev.decision.reasons),
        audit_rows=[AuditRowOut(rule_triggered=r.rule, required_approver=r.approver, decision_reason=r.reason) for r in ev.decision.rules],
        validation_error=ev.validation_error, policy_version=policy.version,
    )
