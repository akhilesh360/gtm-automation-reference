from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health(pipeline_db):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db_ok"] and body["sf_enabled"] is False and body["ai_enabled"] is False


def test_score_account_inline():
    r = client.post("/score-account", json={"account_name": "X", "intent_score": 90, "usage_score": 90,
                                            "engagement_score": 80, "firmographic_fit_score": 80})
    assert r.status_code == 200
    assert r.json()["priority_score"] == 87.0 and r.json()["account_tier"] == "Tier 1"


def test_score_account_by_id(pipeline_db):
    r = client.post("/score-account", json={"account_id": "ACC-00003"})
    assert r.status_code == 200 and r.json()["account_tier"] == "Tier 1"


def test_score_account_missing_inputs():
    assert client.post("/score-account", json={"account_name": "X"}).status_code == 422


def test_evaluate_quote_auto_approved(pipeline_db):
    r = client.post("/evaluate-quote", json={"account_name": "Acme AI", "product_id": "PRD-API-STARTER", "monthly_commitment": 5000,
                                             "contract_term_months": 12, "discount_percent": 5, "payment_terms": "Net 30"})
    assert r.status_code == 200
    body = r.json()
    assert body["approval"]["status"] == "Auto-Approved" and body["economics"]["annual_contract_value"] == 57000
    assert [a["rule_triggered"] for a in body["audit_rows"]] == ["STANDARD_POLICY"]


def test_evaluate_quote_validation_failure(pipeline_db):
    r = client.post("/evaluate-quote", json={"account_name": "Bad", "product_id": "PRD-API-STARTER", "monthly_commitment": 5000,
                                             "contract_term_months": 12, "discount_percent": 150, "payment_terms": "Net 30"})
    assert r.status_code == 200
    assert r.json()["approval"]["status"] == "Failed Validation" and r.json()["validation_error"]
