from src.salesforce.client import MockSalesforceClient


def test_upsert_is_idempotent_by_external_id(tmp_path):
    sf = MockSalesforceClient(tmp_path / "sf.json")
    a = sf.upsert("Account", "External_Account_Id__c", "ACC-1", {"Name": "A"})
    b = sf.upsert("Account", "External_Account_Id__c", "ACC-1", {"Name": "A2"})
    assert a == b and len(sf.table("Account")) == 1 and sf.table("Account")[a]["Name"] == "A2"


def test_flow_b_emulation_creates_exactly_one_task_for_tier1(tmp_path):
    sf = MockSalesforceClient(tmp_path / "sf.json")
    acct = sf.upsert("Account", "External_Account_Id__c", "ACC-1", {"Name": "A", "OwnerId": "Elena"})
    for _ in range(3):  # repeated syncs must not duplicate the Task
        sf.upsert("Account_Score__c", "Score_Id__c", "SC-1", {"Account__c": acct, "Account_Tier__c": "Tier 1",
                                                              "Priority_Score__c": 87, "Task_Description__c": "call them"})
    tasks = sf.query(f"SELECT Id, Status, Description FROM Task WHERE WhatId = '{acct}' AND Priority = 'High'")
    assert len(tasks) == 1 and tasks[0]["Description"] == "call them"


def test_flow_b_emulation_skips_tier2(tmp_path):
    sf = MockSalesforceClient(tmp_path / "sf.json")
    acct = sf.upsert("Account", "External_Account_Id__c", "ACC-2", {"Name": "B"})
    sf.upsert("Account_Score__c", "Score_Id__c", "SC-2", {"Account__c": acct, "Account_Tier__c": "Tier 2"})
    assert sf.query("SELECT Id FROM Task") == []
    assert sf.table("Account")[acct]["Account_Tier__c"] == "Tier 2"


def test_flow_b_emulation_creates_new_task_after_completion(tmp_path):
    sf = MockSalesforceClient(tmp_path / "sf.json")
    acct = sf.upsert("Account", "External_Account_Id__c", "ACC-3", {"Name": "C"})
    sf.upsert("Account_Score__c", "Score_Id__c", "SC-3", {"Account__c": acct, "Account_Tier__c": "Tier 1"})
    tid = sf.query("SELECT Id FROM Task")[0]["Id"]
    sf.table("Task")[tid]["Status"] = "Completed"
    sf.upsert("Account_Score__c", "Score_Id__c", "SC-3", {"Account__c": acct, "Account_Tier__c": "Tier 1"})
    assert len(sf.query("SELECT Id FROM Task")) == 2
