# Salesforce setup (optional)

The full local run runs offline. Follow this only to push records into a real Developer Org.

## 1. Deploy the metadata

```bash
cd sfdx
sf org login web -a gtm-dev
sf project deploy start -d force-app -o gtm-dev
sf org assign permset -n GTM_Automation -o gtm-dev
```

This creates `Quote__c`, `Quote_Line__c`, `Account_Score__c`, `Approval_Audit__c`, `Integration_Log__c`, four custom fields on `Account`, the `GTM_Settings__c` custom setting, the `GTM_Automation` permission set, and two Flows.

## 2. Configure the RevOps test mailbox

Setup → Custom Settings → GTM Settings → Manage → New (organization default) → set **RevOps Notification Email** to a mailbox you can read. Flow A emails the Quote Owner plus this address.

## 3. Point the Python engine at the org

A real Salesforce client that authenticates with Salesforce credentials or an access token; a mock client supports offline development and testing. The default mode obtains an access token from the Salesforce CLI login, so no password or security token is stored anywhere:

```bash
SF_ENABLED=true python -m src.main run-all
```

That works as long as `sf org login web -a gtm-dev` has been run once on the machine. To use a different alias, set `SF_ALIAS`. To use username/password/token instead (for example on a server without the CLI), copy `.env.example` to `.env` and set:

```
SF_ENABLED=true
SF_AUTH=password
SF_USERNAME=you@example.com
SF_PASSWORD=...
SF_SECURITY_TOKEN=...
SF_DOMAIN=login
```

Notes from a verified run against a Developer Edition org:

- Account records are owned by the integration user. The `account_owner` names in the CSV are kept locally and used by the mock only, because Salesforce `OwnerId` must be a User Id.
- Quotes that failed validation with a payment term outside the allowed picklist are synced with a blank `Payment_Terms__c`; the bad value stays in `Exception_Reason__c`.
- Flow A fires on new quotes and on status changes (`ISNEW() || ISCHANGED(Approval_Status__c)`). Re-syncing an unchanged quote does not re-send email.

`sync-salesforce` upserts Accounts, Account Scores, Quotes and Approval Audits by external ID. `sync-task-outcomes` reads back the Tasks that Flow B created.

## What the Flows do

**Flow A · Quote Approval Notification** (record-triggered on `Quote__c`, when `Approval_Status__c` changes)

1. Checks required fields are present (commitment, term, discount, payment terms, approval status). If not, emails the Quote Owner.
2. `Pending Approval` → emails the Quote Owner and the RevOps test mailbox with the route and reasons written by Python, then stamps `Approval_Requested_At__c`.
3. `Auto-Approved` → stamps `Approved_At__c`.
4. `Failed Validation` → emails the Quote Owner.

It contains no discount, ACV or payment-term logic. In v1, role routing is displayed on the quote and emailed to the Quote Owner plus a configured RevOps test mailbox. Production role-to-user or role-to-queue mapping is deferred to v2, as is capturing a human approve/reject decision.

**Flow B · Tier 1 Task Creation** (record-triggered on `Account_Score__c`)

1. If `Account_Tier__c` is not `Tier 1`, only updates the Account's tier, score and last-signal date.
2. Otherwise looks for an open High-priority Task on the Account. If one exists, does nothing more.
3. Otherwise creates a Task for the Account Owner with Subject "High-priority account follow-up" and Description = `Task_Description__c`.

It reads the tier Python assigned; it does not compare the score to a threshold.

## v2 additions

`Quote__c` gains `Approver__c`, `Rejection_Reason__c`, `ERP_Order_Id__c`, `ERP_Status__c`, `ERP_Sent_At__c`. Flow A has two more branches: `Approved` stamps `Approved_At__c` and `Approver__c` (from the editing user when blank); `Rejected` emails the Quote Owner with the reason. To approve a quote, a user edits `Approval_Status__c` on the record; `python -m src.main sync-approval-outcomes` pulls the decision into DuckDB and `erp-handoff` sends approved quotes to the ERP and writes the order id and status back. The quote sync never overwrites an `Approved`/`Rejected` status set in Salesforce.

## Local mode

With `SF_ENABLED=false`, `MockSalesforceClient` persists to `data/processed/mock_salesforce.json` and emulates Flow B (one Task per Tier 1 Account, deduped on open High-priority Tasks), so the scenario run behaves the same way without an org.
