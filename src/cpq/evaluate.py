"""End-to-end quote evaluation: validate -> price -> route. Pure; persistence lives in src/cpq/audit.py."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.cpq.approval_rules import RULE_FAILED, determine_approval_route
from src.cpq.models import ApprovalDecision, AuditRule, PricedQuote, Product, QuoteRequest, ValidationError
from src.cpq.pricing_engine import price_quote
from src.cpq.quote_validator import validate_quote
from src.policy import Policy


@dataclass
class QuoteEvaluation:
    request: QuoteRequest
    product: Optional[Product]
    priced: Optional[PricedQuote]
    decision: ApprovalDecision
    validation_error: Optional[str] = None

    @property
    def status(self) -> str:
        return self.decision.status


def evaluate_quote(request: QuoteRequest, product: Optional[Product], policy: Policy) -> QuoteEvaluation:
    try:
        validate_quote(request, product, policy)
    except ValidationError as e:
        rule = AuditRule(RULE_FAILED, None, str(e))
        decision = ApprovalDecision("Failed Validation", approvers=[], reasons=[str(e)], rules=[rule])
        return QuoteEvaluation(request, product, None, decision, validation_error=str(e))
    assert product is not None
    priced = price_quote(request, product)
    decision = determine_approval_route(priced, policy)
    return QuoteEvaluation(request, product, priced, decision)
