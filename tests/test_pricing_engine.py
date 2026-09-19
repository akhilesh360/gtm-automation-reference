from src.cpq.models import QuoteRequest
from src.cpq.pricing_engine import calculate_quote, calculate_usage_pricing, price_quote


def test_calculate_quote_basic():
    e = calculate_quote(5000, 1, 5, 12)
    assert (e.gross_contract_value, e.discount_amount, e.net_contract_value, e.annual_contract_value) == (60000, 3000, 57000, 57000)


def test_acv_annualizes_multi_year():
    e = calculate_quote(10000, 1, 0, 24)
    assert e.gross_contract_value == 240000 and e.annual_contract_value == 120000


def test_usage_pricing_with_overage():
    u = calculate_usage_pricing(10000, 10_000_000, 15_000_000, 0.0000012, 12)
    assert u.overage_units == 5_000_000
    assert u.monthly_overage == 6.0
    assert u.monthly_total == 10006.0
    assert u.total_contract_value == 120072.0


def test_usage_pricing_no_overage_when_under_allowance():
    u = calculate_usage_pricing(50000, 50_000_000, 45_000_000, 0.0000010, 12)
    assert u.overage_units == 0 and u.monthly_overage == 0 and u.total_contract_value == 600000


def test_custom_overage_rate_replaces_product_rate(products):
    req = QuoteRequest(account_name="X", product_id="PRD-API-BASE", monthly_commitment=10000, contract_term_months=12,
                       discount_percent=0, payment_terms="Net 30", forecasted_units=20_000_000, custom_overage_rate=0.0000020)
    p = price_quote(req, products["PRD-API-BASE"])
    assert p.usage.overage_units == 10_000_000
    assert p.usage.monthly_overage == 20.0        # 10M * 0.0000020, not 12.0 at the list rate
    assert p.effective_list_price == 10020.0


def test_subscription_product_has_no_usage(products):
    req = QuoteRequest(account_name="X", product_id="PRD-SUPPORT-PREM", monthly_commitment=2000, contract_term_months=12,
                       discount_percent=0, payment_terms="Net 30")
    p = price_quote(req, products["PRD-SUPPORT-PREM"])
    assert p.usage is None and p.economics.gross_contract_value == 24000
