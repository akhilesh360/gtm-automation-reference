"""Scenario 4: human approval in Salesforce -> outcome sync -> ERP handoff -> reconciliation, in mock mode."""
import duckdb
import pytest

from src.erp.handoff import handoff_approved_quotes
from src.erp.netsuite_mock import MockNetSuiteClient
from src.salesforce.client import MockSalesforceClient
from src.salesforce.sync import record_decision, sync_approval_outcomes, write_erp_status


def _db(pipeline_db):
    return duckdb.connect(str(pipeline_db))


def test_auto_approved_quotes_are_handed_off_and_reconciled(pipeline_db):
    con = _db(pipeline_db)
    r = con.execute("SELECT erp_status, erp_order_id FROM quotes WHERE quote_id = 'Q-00001'").fetchone()
    assert r[0] == "Reconciled" and r[1].startswith("SO-")
    o = con.execute("SELECT status, accepted_total FROM erp_orders WHERE quote_id = 'Q-00001'").fetchone()
    assert o[0] == "RECONCILED" and float(o[1]) == 57000.0
    con.close()


def test_pending_quotes_are_never_sent(pipeline_db):
    con = _db(pipeline_db)
    n = con.execute("SELECT COUNT(*) FROM erp_orders o JOIN quotes q ON q.quote_id = o.quote_id "
                    "WHERE q.approval_status NOT IN ('Auto-Approved','Approved')").fetchone()[0]
    assert n == 0
    con.close()


def test_human_approval_flows_to_erp(pipeline_db, tmp_path):
    from src.config import settings
    con = _db(pipeline_db)
    sf = MockSalesforceClient()  # same store the pipeline used
    erp = MockNetSuiteClient()
    before = con.execute("SELECT approval_status FROM quotes WHERE quote_id = 'Q-00002'").fetchone()[0]
    if before == "Pending Approval":
        record_decision(con, sf, "Q-00002", "Approved", "Jane Doe")
        assert sync_approval_outcomes(con, sf, "run-t") == 1
        handoff_approved_quotes(con, erp, "run-t")
    r = con.execute("SELECT approval_status, approver, erp_status FROM quotes WHERE quote_id = 'Q-00002'").fetchone()
    assert r == ("Approved", "Jane Doe", "Reconciled")
    audit = con.execute("SELECT approver, decision FROM approval_audit WHERE quote_id = 'Q-00002' AND rule_triggered = 'HUMAN_DECISION'").fetchall()
    assert audit == [("Jane Doe", "Approved")]
    sfq = sf.query("SELECT Approval_Status__c, Approver__c, Approved_At__c FROM Quote__c WHERE Quote_Number__c = 'Q-00002'")[0]
    assert sfq["Approval_Status__c"] == "Approved" and sfq["Approver__c"] == "Jane Doe" and sfq["Approved_At__c"]
    write_erp_status(con, sf, "run-t")
    assert sf.query("SELECT ERP_Status__c FROM Quote__c WHERE Quote_Number__c = 'Q-00002'")[0]["ERP_Status__c"] == "Reconciled"
    con.close()


def test_decide_rejects_non_pending(pipeline_db):
    con = _db(pipeline_db)
    with pytest.raises(ValueError):
        record_decision(con, MockSalesforceClient(), "Q-00001", "Approved", "Jane Doe")  # auto-approved, not pending
    con.close()


def test_rejected_quote_gets_audit_row_and_no_order(pipeline_db):
    con = _db(pipeline_db)
    sf = MockSalesforceClient(); erp = MockNetSuiteClient()
    qid = con.execute("SELECT quote_id FROM quotes WHERE approval_status = 'Pending Approval' AND quote_id <> 'Q-00002' LIMIT 1").fetchone()[0]
    record_decision(con, sf, qid, "Rejected", "Finance Lead", reason="Margin below floor")
    sync_approval_outcomes(con, sf, "run-t")
    handoff_approved_quotes(con, erp, "run-t")
    r = con.execute("SELECT approval_status, rejection_reason, erp_status FROM quotes WHERE quote_id = ?", [qid]).fetchone()
    assert r[0] == "Rejected" and r[1] == "Margin below floor" and r[2] == "Not Sent"
    assert con.execute("SELECT COUNT(*) FROM erp_orders WHERE quote_id = ?", [qid]).fetchone()[0] == 0
    con.close()
