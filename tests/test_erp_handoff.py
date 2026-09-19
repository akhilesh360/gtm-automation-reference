from datetime import date

import pytest

from src.erp.netsuite_mock import ErpError, MockNetSuiteClient, validate_payload
from src.erp.payload import billing_schedule, build_sales_order


def _quote(**kw):
    q = dict(quote_id="Q-T1", account_id="ACC-1", account_name="EnterpriseGen", product_id="PRD-ENT-PLATFORM", quantity=1,
             contract_term_months=12, discount_percent=25.0, payment_terms="Net 60", forecasted_units=45_000_000,
             custom_overage_rate=0.000001, effective_list_price=50000.0, gross_contract_value=600000.0,
             discount_amount=150000.0, net_contract_value=450000.0, annual_contract_value=450000.0)
    q.update(kw)
    return q


PRODUCT = {"product_id": "PRD-ENT-PLATFORM", "product_name": "Enterprise Platform", "pricing_model": "usage",
           "included_units": 50_000_000, "overage_price_per_unit": 0.0000012}


def test_billing_schedule_monthly_sums_exactly():
    lines = billing_schedule(450000.0, 12, "Net 60", date(2026, 10, 1))
    assert len(lines) == 12 and round(sum(line["amount"] for line in lines), 2) == 450000.0
    assert lines[0]["due_date"] == "2026-10-01" and lines[-1]["due_date"] == "2027-09-01"


def test_billing_schedule_rounding_absorbed_in_last_line():
    lines = billing_schedule(100.0, 3, "Net 30", date(2026, 1, 31))
    assert [line["amount"] for line in lines] == [33.33, 33.33, 33.34]
    assert lines[1]["due_date"] == "2026-02-28"


def test_billing_schedule_prepaid_is_single_line():
    lines = billing_schedule(57000.0, 12, "Annual Prepaid", date(2026, 10, 1))
    assert len(lines) == 1 and lines[0]["amount"] == 57000.0


def test_payload_shape_and_custom_overage():
    p = build_sales_order(_quote(), {"sf_account_id": "001X"}, PRODUCT, "2026.09", "run-1", start=date(2026, 10, 1))
    assert p["external_quote_id"] == "Q-T1" and p["customer"]["salesforce_account_id"] == "001X"
    assert p["lines"][0]["net_monthly_rate"] == 37500.0 and p["lines"][0]["amount"] == 450000.0
    assert p["usage"]["custom_overage"] is True and p["usage"]["overage_rate"] == 0.000001
    assert len(p["billing_schedule"]) == 12
    validate_payload(p)


def test_validate_rejects_schedule_mismatch():
    p = build_sales_order(_quote(), {}, PRODUCT, "2026.09", "run-1", start=date(2026, 10, 1))
    p["billing_schedule"][0]["amount"] += 10
    with pytest.raises(ErpError):
        validate_payload(p)


def test_mock_erp_is_idempotent_by_quote(tmp_path):
    erp = MockNetSuiteClient(tmp_path / "erp.json")
    p = build_sales_order(_quote(), {}, PRODUCT, "2026.09", "run-1", start=date(2026, 10, 1))
    a = erp.create_sales_order(p)
    b = erp.create_sales_order(p)
    assert a["sales_order_id"] == b["sales_order_id"] and a["duplicate"] is False and b["duplicate"] is True
    assert a["accepted_total"] == 450000.0 and erp.get_sales_order(a["sales_order_id"])["customer"] == "EnterpriseGen"


def test_mock_erp_rejects_invalid_payload(tmp_path):
    erp = MockNetSuiteClient(tmp_path / "erp.json")
    with pytest.raises(ErpError):
        erp.create_sales_order({"external_quote_id": "Q-X"})
