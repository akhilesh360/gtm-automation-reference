"""Approval routing. Every threshold comes from the Policy object (config/policy.yaml)."""
from __future__ import annotations

from src.cpq.models import ApprovalDecision, AuditRule, PricedQuote
from src.policy import Policy

RULE_DISCOUNT_MANAGER = "DISCOUNT_GT_10"
RULE_DISCOUNT_EXEC = "DISCOUNT_GT_20"
RULE_ACV = "ACV_GTE_100K"
RULE_TERMS = "NONSTANDARD_TERMS"
RULE_CUSTOM = "CUSTOM_PRICING"
RULE_STANDARD = "STANDARD_POLICY"
RULE_FAILED = "FAILED_VALIDATION"


def _ordered_unique(names: list[str], order: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in sorted(names, key=lambda n: order.index(n) if n in order else len(order)):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def determine_approval_route(q: PricedQuote, policy: Policy) -> ApprovalDecision:
    rules: list[AuditRule] = []
    d, acv = q.discount_percent, q.annual_contract_value
    has_custom_pricing = q.has_custom_pricing  # custom checkbox OR custom overage rate; never mutates the request

    if d > policy.discount.manager_limit:
        reason = f"Discount exceeds {policy.discount.manager_limit:g}%"
        rules += [AuditRule(RULE_DISCOUNT_EXEC, "RevOps", reason), AuditRule(RULE_DISCOUNT_EXEC, "Finance", reason)]
    elif d > policy.discount.standard_limit:
        rules += [AuditRule(RULE_DISCOUNT_MANAGER, "Sales Manager", f"Discount exceeds standard {policy.discount.standard_limit:g}% threshold")]

    if acv >= policy.acv.vp_threshold:
        rules += [AuditRule(RULE_ACV, "VP Sales", f"ACV exceeds ${policy.acv.vp_threshold:,.0f}")]

    if q.payment_terms not in policy.payment_terms.standard:
        rules += [AuditRule(RULE_TERMS, "Finance", "Nonstandard payment terms")]

    if has_custom_pricing:
        rules += [AuditRule(RULE_CUSTOM, "RevOps", "Custom product, commitment, or overage rate")]

    if not rules:
        std = AuditRule(RULE_STANDARD, None, "Quote meets standard commercial policy")
        return ApprovalDecision("Auto-Approved", approvers=[], reasons=[std.reason], rules=[std])

    approvers = _ordered_unique([r.approver for r in rules if r.approver], policy.approver_order)
    reasons: list[str] = []
    for r in rules:
        if r.reason not in reasons:
            reasons.append(r.reason)
    return ApprovalDecision("Pending Approval", approvers=approvers, reasons=reasons, rules=rules)
