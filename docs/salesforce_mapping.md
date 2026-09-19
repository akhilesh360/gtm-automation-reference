# Salesforce object and field mapping

Salesforce is the CRM of record and the execution layer. The Python engine writes decisions; Flows execute CRM actions. Nothing in Salesforce recomputes a price, discount threshold or approval route.

| Business entity | Salesforce object | External ID | Written by |
|---|---|---|---|
| Customer | `Account` (standard) | `External_Account_Id__c` | `upsert_accounts` |
| Quote (CPQ-style) | `Quote__c` (custom) | `Quote_Number__c` | `create_quotes` |
| Quote line | `Quote_Line__c` | — | reserved for v2 |
| Product | `Product2` (standard; v1 stores `Product_Id__c` text on the quote) | — | — |
| Account score | `Account_Score__c` | `Score_Id__c` | `upsert_scores` |
| Approval/audit event | `Approval_Audit__c` (master-detail to `Quote__c`) | `Audit_Id__c` | `create_quotes` |
| Sales task | `Task` (standard) | — | **Flow B only** |
| Integration log | `Integration_Log__c` | `Log_Id__c` | `mirror_integration_log` |
| Settings | `GTM_Settings__c` (hierarchy custom setting) | — | admin, once |

## DuckDB → Salesforce field map

### `quotes` → `Quote__c`

| DuckDB | Salesforce |
|---|---|
| quote_id | Quote_Number__c |
| account_id → accounts.sf_account_id | Account__c |
| product_id | Product_Id__c |
| monthly_commitment | Monthly_Commitment__c |
| effective_list_price | List_Price__c |
| quantity | Quantity__c |
| contract_term_months | Contract_Term_Months__c |
| discount_percent | Discount_Percent__c |
| discount_amount | Discount_Amount__c |
| net_contract_value | Net_Price__c |
| annual_contract_value | Annual_Contract_Value__c |
| payment_terms | Payment_Terms__c |
| custom_pricing (incl. custom overage) | Custom_Pricing__c |
| approval_status | Approval_Status__c |
| approval_route | Approval_Route__c |
| exception_reason | Exception_Reason__c |
| policy_version | Policy_Version__c |
| — (set by Flow A) | Approval_Requested_At__c, Approved_At__c |

### `approval_audit` → `Approval_Audit__c`

audit_id → Audit_Id__c; quote_id → Quote__c; rule_triggered → Rule_Triggered__c; requested_discount → Requested_Discount__c; required_approver → Required_Approver__c; decision → Decision__c; decision_reason → Decision_Reason__c; decision_timestamp → Decision_Timestamp__c; approver → Approver__c; policy_version → Policy_Version__c; correlation_id → Correlation_Id__c.

### `account_scores` → `Account_Score__c`

score_id → Score_Id__c; account_id → Account__c; intent_score → Intent_Score__c; engagement_score → Engagement_Score__c; firmographic_fit_score → Firmographic_Fit_Score__c; usage_score → Usage_Score__c; priority_score → Priority_Score__c; account_tier → Account_Tier__c; scoring_reason → Scoring_Reason__c; narrative → Narrative__c; task_description → Task_Description__c; scored_at → Scored_At__c.

### Account custom fields (updated by Flow B)

`External_Account_Id__c`, `Account_Tier__c`, `Priority_Score__c`, `Last_Signal_Date__c`.

## Ownership statement

Python owns decisioning; Salesforce Flow owns CRM-native task creation and duplicate prevention.

| Action | Owner |
|---|---|
| Price, discount, ACV, approval route, status, audit rows | Python (`config/policy.yaml`) |
| Approval notification email, timestamps | Flow A |
| Task creation, open-task dedupe, Account tier fields | Flow B |
| Reading Task Ids back into DuckDB | `sync-task-outcomes` |
