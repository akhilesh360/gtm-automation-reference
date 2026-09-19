"""Salesforce client abstraction. Mock (default) and real (SF_ENABLED=true) share one interface.

The mock persists to data/processed/mock_salesforce.json and EMULATES FLOW B: on an Account_Score__c upsert with
Account_Tier__c = 'Tier 1' it creates a Task unless an open High-priority Task already exists for that Account.
Python never creates a Task directly in either mode.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from src.config import settings


class SalesforceClient(Protocol):
    name: str

    def upsert(self, sobject: str, external_id_field: str, external_id: str, data: dict[str, Any]) -> str: ...
    def create(self, sobject: str, data: dict[str, Any]) -> str: ...
    def query(self, soql: str) -> list[dict[str, Any]]: ...


class MockSalesforceClient:
    name = "mock"

    def __init__(self, path: Path | None = None):
        self.path = path or settings.mock_sf_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db: dict[str, dict[str, dict[str, Any]]] = {}
        if self.path.exists():
            try:
                self._db = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._db = {}

    # ---- persistence ----
    def _save(self) -> None:
        self.path.write_text(json.dumps(self._db, indent=2, default=str), encoding="utf-8")

    def reset(self) -> None:
        self._db = {}
        self._save()

    def table(self, sobject: str) -> dict[str, dict[str, Any]]:
        return self._db.setdefault(sobject, {})

    # ---- API ----
    def upsert(self, sobject: str, external_id_field: str, external_id: str, data: dict[str, Any]) -> str:
        tbl = self.table(sobject)
        existing = next((rid for rid, rec in tbl.items() if rec.get(external_id_field) == external_id), None)
        rid = existing or self._new_id(sobject)
        rec = {**tbl.get(rid, {}), **data, external_id_field: external_id, "Id": rid,
               "LastModifiedDate": datetime.now().isoformat(timespec="seconds")}
        tbl[rid] = rec
        if sobject == "Account_Score__c":
            self._emulate_flow_b(rec)
        self._save()
        return rid

    def create(self, sobject: str, data: dict[str, Any]) -> str:
        rid = self._new_id(sobject)
        self.table(sobject)[rid] = {**data, "Id": rid, "CreatedDate": datetime.now().isoformat(timespec="seconds")}
        self._save()
        return rid

    def query(self, soql: str) -> list[dict[str, Any]]:
        """Supports the small SOQL subset the sync modules use: SELECT ... FROM X [WHERE a = 'v' [AND ...]]."""
        m = re.match(r"SELECT\s+(.+?)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+))?$", soql.strip(), re.I | re.S)
        if not m:
            raise ValueError(f"Mock SOQL cannot parse: {soql}")
        fields = [f.strip() for f in m.group(1).split(",")]
        rows = list(self.table(m.group(2)).values())
        if m.group(3):
            for cond in re.split(r"\s+AND\s+", m.group(3), flags=re.I):
                cm = re.match(r"(\w+)\s*(=|!=)\s*'([^']*)'", cond.strip())
                if not cm:
                    raise ValueError(f"Mock SOQL cannot parse condition: {cond}")
                k, op, v = cm.groups()
                rows = [r for r in rows if (str(r.get(k)) == v) == (op == "=")]
        return [{f: r.get(f) for f in fields} for r in rows]

    # ---- helpers ----
    def _new_id(self, sobject: str) -> str:
        prefix = {"Account": "001", "Task": "00T", "Quote__c": "a0Q", "Account_Score__c": "a0S",
                  "Approval_Audit__c": "a0A", "Integration_Log__c": "a0L"}.get(sobject, "a0X")
        return prefix + uuid.uuid4().hex[:15].upper()

    def _emulate_flow_b(self, score: dict[str, Any]) -> None:
        account_id = score.get("Account__c")
        if not account_id:
            return
        acct = self.table("Account").get(account_id, {})
        acct.update({"Account_Tier__c": score.get("Account_Tier__c"), "Priority_Score__c": score.get("Priority_Score__c"),
                     "Last_Signal_Date__c": datetime.now().date().isoformat()})
        self.table("Account")[account_id] = acct
        if score.get("Account_Tier__c") != "Tier 1":
            return
        open_high = [t for t in self.table("Task").values()
                     if t.get("WhatId") == account_id and t.get("Priority") == "High" and t.get("Status") != "Completed"]
        if open_high:
            return
        self.create("Task", {
            "WhatId": account_id, "OwnerId": acct.get("OwnerId"), "Subject": "High-priority account follow-up",
            "Description": score.get("Task_Description__c") or score.get("Scoring_Reason__c"),
            "Priority": "High", "Status": "Not Started", "CreatedBy": "Flow: Tier1_Task_Creation (mock emulation)",
        })


class RealSalesforceClient:
    name = "salesforce"

    def __init__(self):
        from simple_salesforce import Salesforce  # imported lazily so the mock path has no dependency

        self.sf = Salesforce(username=settings.sf_username, password=settings.sf_password,
                             security_token=settings.sf_security_token, domain=settings.sf_domain)

    def upsert(self, sobject: str, external_id_field: str, external_id: str, data: dict[str, Any]) -> str:
        obj = getattr(self.sf, sobject)
        res = obj.upsert(f"{external_id_field}/{external_id}", {k: v for k, v in data.items() if k != external_id_field})
        if isinstance(res, dict) and res.get("id"):
            return res["id"]
        rows = self.sf.query(f"SELECT Id FROM {sobject} WHERE {external_id_field} = '{external_id}'")["records"]
        return rows[0]["Id"] if rows else ""

    def create(self, sobject: str, data: dict[str, Any]) -> str:
        return getattr(self.sf, sobject).create(data)["id"]

    def query(self, soql: str) -> list[dict[str, Any]]:
        return [{k: v for k, v in r.items() if k != "attributes"} for r in self.sf.query_all(soql)["records"]]


def get_client() -> SalesforceClient:
    if settings.sf_enabled:
        return RealSalesforceClient()
    return MockSalesforceClient()
