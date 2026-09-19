"""Sync DuckDB decisions to Salesforce (mock or real). Upserts by external ID; retries with backoff; logs every call."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable

import duckdb

from src.monitoring.logger import (STATUS_FAILED_API, STATUS_RETRYING, STATUS_SUCCESS, get_logger, write_integration_log)
from src.salesforce.client import SalesforceClient

MAX_RETRIES = 3


def _with_retry(con: duckdb.DuckDBPyConnection, workflow: str, record_type: str, record_id: str,
                correlation_id: str, fn: Callable[[], Any]) -> Any:
    log = get_logger()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = fn()
            write_integration_log(con, workflow, STATUS_SUCCESS, correlation_id, record_type, record_id, retry_count=attempt - 1)
            return result
        except Exception as e:  # noqa: BLE001
            if attempt < MAX_RETRIES:
                write_integration_log(con, workflow, STATUS_RETRYING, correlation_id, record_type, record_id, error=str(e), retry_count=attempt)
                log.warning("retrying", extra={"workflow": workflow, "record_id": record_id, "status": STATUS_RETRYING, "correlation_id": correlation_id})
                time.sleep(0.2 * attempt)
            else:
                write_integration_log(con, workflow, STATUS_FAILED_API, correlation_id, record_type, record_id, error=str(e), retry_count=attempt)
                log.error("sync failed", extra={"workflow": workflow, "record_id": record_id, "status": STATUS_FAILED_API, "correlation_id": correlation_id})
                raise


def upsert_accounts(con: duckdb.DuckDBPyConnection, sf: SalesforceClient, correlation_id: str) -> int:
    rows = con.execute("SELECT account_id, account_name, domain, industry, employee_count, account_owner FROM accounts").fetchall()
    n = 0
    for aid, name, domain, industry, emp, owner in rows:
        data = {"Name": name, "Website": domain, "Industry": industry, "NumberOfEmployees": emp, "OwnerId": owner}
        sf_id = _with_retry(con, "upsert_accounts", "Account", aid, correlation_id,
                            lambda: sf.upsert("Account", "External_Account_Id__c", aid, data))
        con.execute("UPDATE accounts SET sf_account_id = ? WHERE account_id = ?", [sf_id, aid])
        n += 1
    return n


def upsert_scores(con: duckdb.DuckDBPyConnection, sf: SalesforceClient, correlation_id: str) -> int:
    rows = con.execute(
        """SELECT s.score_id, s.account_id, a.sf_account_id, s.intent_score, s.engagement_score, s.firmographic_fit_score,
                  s.usage_score, s.priority_score, s.account_tier, s.scoring_reason, s.narrative, s.task_description, s.scored_at
           FROM account_scores s JOIN accounts a ON a.account_id = s.account_id"""
    ).fetchall()
    n = 0
    for r in rows:
        score_id, account_id, sf_acct = r[0], r[1], r[2]
        data = {"Account__c": sf_acct, "Intent_Score__c": r[3], "Engagement_Score__c": r[4], "Firmographic_Fit_Score__c": r[5],
                "Usage_Score__c": r[6], "Priority_Score__c": r[7], "Account_Tier__c": r[8], "Scoring_Reason__c": r[9],
                "Narrative__c": r[10], "Task_Description__c": r[11], "Scored_At__c": str(r[12])}
        _with_retry(con, "upsert_scores", "Account_Score__c", score_id, correlation_id,
                    lambda: sf.upsert("Account_Score__c", "Score_Id__c", score_id, data))
        n += 1
    return n


def create_quotes(con: duckdb.DuckDBPyConnection, sf: SalesforceClient, correlation_id: str) -> int:
    rows = con.execute(
        """SELECT q.quote_id, a.sf_account_id, q.product_id, q.monthly_commitment, q.effective_list_price, q.quantity,
                  q.contract_term_months, q.discount_percent, q.discount_amount, q.net_contract_value, q.annual_contract_value,
                  q.payment_terms, q.custom_pricing, q.approval_status, q.approval_route, q.exception_reason, q.policy_version
           FROM quotes q JOIN accounts a ON a.account_id = q.account_id"""
    ).fetchall()
    n = 0
    for r in rows:
        quote_id = r[0]
        data = {"Account__c": r[1], "Product_Id__c": r[2], "Monthly_Commitment__c": r[3], "List_Price__c": r[4], "Quantity__c": r[5],
                "Contract_Term_Months__c": r[6], "Discount_Percent__c": r[7], "Discount_Amount__c": r[8], "Net_Price__c": r[9],
                "Annual_Contract_Value__c": r[10], "Payment_Terms__c": r[11], "Custom_Pricing__c": bool(r[12]),
                "Approval_Status__c": r[13], "Approval_Route__c": r[14], "Exception_Reason__c": r[15], "Policy_Version__c": r[16]}
        sf_id = _with_retry(con, "create_quotes", "Quote__c", quote_id, correlation_id,
                            lambda: sf.upsert("Quote__c", "Quote_Number__c", quote_id, data))
        con.execute("UPDATE quotes SET sf_quote_id = ? WHERE quote_id = ?", [sf_id, quote_id])
        audits = con.execute(
            "SELECT audit_id, rule_triggered, requested_discount, required_approver, decision, decision_reason, decision_timestamp, policy_version "
            "FROM approval_audit WHERE quote_id = ?", [quote_id]).fetchall()
        for a in audits:
            adata = {"Quote__c": sf_id, "Rule_Triggered__c": a[1], "Requested_Discount__c": a[2], "Required_Approver__c": a[3],
                     "Decision__c": a[4], "Decision_Reason__c": a[5], "Decision_Timestamp__c": str(a[6]), "Policy_Version__c": a[7],
                     "Correlation_Id__c": correlation_id}
            _with_retry(con, "create_quotes", "Approval_Audit__c", a[0], correlation_id,
                        lambda: sf.upsert("Approval_Audit__c", "Audit_Id__c", a[0], adata))
        n += 1
    return n


STATUS_MAP = {"Not Started": "open", "In Progress": "open", "Completed": "completed"}


def sync_task_outcomes(con: duckdb.DuckDBPyConnection, sf: SalesforceClient, correlation_id: str) -> int:
    """Read Flow-created Task Ids/status back into sales_tasks. Local rows stay 'planned' until a Task is found."""
    rows = con.execute(
        "SELECT t.task_id, t.account_id, a.sf_account_id FROM sales_tasks t JOIN accounts a ON a.account_id = t.account_id "
        "WHERE t.priority = 'High'").fetchall()
    n = 0
    for task_id, account_id, sf_acct in rows:
        if not sf_acct:
            continue
        found = sf.query(f"SELECT Id, Status FROM Task WHERE WhatId = '{sf_acct}' AND Priority = 'High'")
        open_tasks = [t for t in found if t.get("Status") != "Completed"] or found
        if not open_tasks:
            continue
        t = open_tasks[0]
        status = STATUS_MAP.get(t.get("Status"), "open")
        con.execute("UPDATE sales_tasks SET sf_task_id = ?, status = ?, updated_at = ? WHERE task_id = ?",
                    [t["Id"], status, datetime.now(), task_id])
        n += 1
    write_integration_log(con, "sync_task_outcomes", STATUS_SUCCESS, correlation_id, "Task", None)
    return n


def mirror_integration_log(con: duckdb.DuckDBPyConnection, sf: SalesforceClient, correlation_id: str) -> int:
    rows = con.execute("SELECT log_id, workflow_name, record_type, record_id, status, started_at, completed_at, error_message, retry_count "
                       "FROM integration_log WHERE correlation_id = ?", [correlation_id]).fetchall()
    for r in rows:
        sf.upsert("Integration_Log__c", "Log_Id__c", r[0], {
            "Workflow_Name__c": r[1], "Record_Type__c": r[2], "Record_Id__c": r[3], "Status__c": r[4],
            "Started_At__c": str(r[5]), "Completed_At__c": str(r[6]) if r[6] else None, "Error_Message__c": r[7],
            "Retry_Count__c": r[8], "Correlation_Id__c": correlation_id})
    return len(rows)
