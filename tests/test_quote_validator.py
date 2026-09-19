import pytest

from src.cpq.models import QuoteRequest, ValidationError
from src.cpq.quote_validator import validate_quote


def _req(**kw):
    base = dict(account_name="Acme", product_id="PRD-API-BASE", monthly_commitment=10000, contract_term_months=12,
                discount_percent=5, payment_terms="Net 30")
    base.update(kw)
    return QuoteRequest(**base)


def test_valid_request_passes(policy, products):
    validate_quote(_req(), products["PRD-API-BASE"], policy)


@pytest.mark.parametrize("kw,msg", [
    (dict(discount_percent=120), "discount_percent"),
    (dict(discount_percent=-1), "discount_percent"),
    (dict(contract_term_months=0), "contract_term_months"),
    (dict(monthly_commitment=0), "monthly_commitment"),
    (dict(payment_terms="Net 45"), "payment_terms"),
    (dict(monthly_commitment=7000), "list price"),
])
def test_rejections(policy, products, kw, msg):
    with pytest.raises(ValidationError) as e:
        validate_quote(_req(**kw), products["PRD-API-BASE"], policy)
    assert msg in str(e.value)


def test_unknown_product_rejected(policy):
    with pytest.raises(ValidationError):
        validate_quote(_req(product_id="NOPE"), None, policy)


def test_commitment_mismatch_allowed_with_custom_pricing(policy, products):
    validate_quote(_req(monthly_commitment=7000, custom_pricing=True), products["PRD-API-BASE"], policy)


def test_commitment_mismatch_allowed_with_custom_overage_rate(policy, products):
    validate_quote(_req(monthly_commitment=7000, custom_overage_rate=0.0000010), products["PRD-API-BASE"], policy)
