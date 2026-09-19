import pytest

from src.cpq.approval_rules import determine_approval_route
from src.cpq.models import QuoteRequest
from src.cpq.pricing_engine import price_quote


def _priced(products, product="PRD-API-STARTER", **kw):
    base = dict(account_name="Acme", product_id=product, monthly_commitment=products[product].list_price_monthly,
                contract_term_months=12, discount_percent=5, payment_terms="Net 30")
    base.update(kw)
    return price_quote(QuoteRequest(**base), products[product])


def test_auto_approve_creates_standard_policy_rule(policy, products):
    d = determine_approval_route(_priced(products), policy)
    assert d.status == "Auto-Approved" and d.approvers == []
    assert [r.rule for r in d.rules] == ["STANDARD_POLICY"] and d.rules[0].approver is None


@pytest.mark.parametrize("disc,expected", [(10, []), (10.01, ["Sales Manager"]), (20, ["Sales Manager"]), (20.01, ["RevOps", "Finance"])])
def test_discount_boundaries(policy, products, disc, expected):
    d = determine_approval_route(_priced(products, discount_percent=disc), policy)
    assert d.approvers == expected


def test_acv_boundary_exactly_100k(policy, products):
    # Starter at $5,000/mo, 24 months, 0% -> ACV 60,000; Base at $10,000/mo, 12 months, 0% -> exactly 120,000 (VP)
    d = determine_approval_route(_priced(products, "PRD-API-BASE", discount_percent=0), policy)
    assert "VP Sales" in d.approvers
    # 16.67% discount on Base -> ACV 99,996 -> no VP
    d2 = determine_approval_route(_priced(products, "PRD-API-BASE", discount_percent=16.67), policy)
    assert "VP Sales" not in d2.approvers and d2.approvers == ["Sales Manager"]


def test_nonstandard_terms_routes_to_finance(policy, products):
    d = determine_approval_route(_priced(products, payment_terms="Net 60"), policy)
    assert d.approvers == ["Finance"]


def test_custom_overage_rate_counts_as_custom_pricing(policy, products):
    d = determine_approval_route(_priced(products, custom_overage_rate=0.0000010, forecasted_units=1000), policy)
    assert d.approvers == ["RevOps"] and [r.rule for r in d.rules] == ["CUSTOM_PRICING"]


def test_enterprise_scenario_has_five_audit_rows_in_order(policy, products):
    d = determine_approval_route(_priced(products, "PRD-ENT-PLATFORM", discount_percent=25, payment_terms="Net 60",
                                         forecasted_units=45_000_000, custom_overage_rate=0.0000010), policy)
    assert d.status == "Pending Approval"
    assert d.approvers == ["RevOps", "Finance", "VP Sales"]
    assert [r.rule for r in d.rules] == ["DISCOUNT_GT_20", "DISCOUNT_GT_20", "ACV_GTE_100K", "NONSTANDARD_TERMS", "CUSTOM_PRICING"]
