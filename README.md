# AI-Native GTM Revenue Operations Engine

A Salesforce-centered reference implementation for CPQ-style pricing governance, discount approvals, signal-based account prioritization, CRM data-quality controls, and revenue operations reporting.

Deterministic Python and SQL make every commercial-policy and scoring decision. An optional AI step drafts prose. Salesforce Flow executes CRM actions. The whole thing runs locally on DuckDB and Streamlit with no credentials, and can optionally sync selected records to a Salesforce org through a deployable SFDX package.

![Architecture](docs/architecture.png)

**Status:** v1 is complete. I tested the seeded scenarios, deployed the Salesforce metadata to a Developer Org, verified the Flow behavior, and confirmed the offline and Salesforce-connected modes.

This is a CPQ-style reference implementation using Salesforce custom objects. It demonstrates commercial-policy and quote-governance patterns.

## What it does

| Module | Flow | Output |
|---|---|---|
| **CPQ-style pricing and approvals** | quote request → validation → pricing (subscription + usage overage) → approval route from `config/policy.yaml` → audit trail → Salesforce custom-object sync | `quotes`, `approval_audit`, `Quote__c`, `Approval_Audit__c` |
| **Signal-based account scoring** | accounts + Clay-shaped enrichment + HubSpot-shaped engagement + usage telemetry → deterministic sub-scores → weighted priority → Tier 1/2/3 → planned task → `Account_Score__c` → Flow B creates the Salesforce Task | `account_scores`, `sales_tasks`, Salesforce Task |
| **Data quality and monitoring** | schema validation, dedupe, quote validator, nine parameterized SQL checks, JSON logs with correlation IDs, retries, integration log | `dq_results`, `integration_log`, exit code for CI |
| **Dashboard and API** | Streamlit (CPQ Operations · Account Prioritization · Data Quality) and FastAPI (`/health`, `/score-account`, `/evaluate-quote`) | local UI, service endpoints |

**Ownership model:** Python owns decisioning; Salesforce Flow owns CRM-native task creation and duplicate prevention. Commercial policy lives in one versioned file, `config/policy.yaml`. Flows contain no thresholds.

## Screenshots

| CPQ Operations | Account Prioritization | Data Quality |
|---|---|---|
| ![CPQ](docs/screenshots/cpq_operations.png) | ![GTM](docs/screenshots/account_prioritization.png) | ![DQ](docs/screenshots/data_quality.png) |

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.main scenarios          # runs the pipeline and prints the three scenarios
streamlit run dashboard/app.py   # dashboard
uvicorn api.app:app --reload     # API docs at http://127.0.0.1:8000/docs
pytest -q                        # 66 tests, no env vars needed
```

No `.env` is required. A real Salesforce client that authenticates with Salesforce credentials or an access token; a mock client supports offline development and testing. To push into a real org, deploy `sfdx/` once (see `docs/salesforce_setup.md`) and run with `SF_ENABLED=true`; by default the real client obtains an access token from the Salesforce CLI login, or set `SF_AUTH=password` to use username, password and security token. Set `AI_ENABLED=true` with an API key for AI-assisted drafting.

## The three test scenarios

| Scenario | Input | Result |
|---|---|---|
| **Alpha AI** | Starter API Commitment, $5,000/mo × 12, 5% discount, Net 30 | ACV $57,000 → **Auto-Approved**, one `STANDARD_POLICY` audit row |
| **EnterpriseGen** | Enterprise Platform, $50,000/mo × 12, 25% discount, Net 60, custom overage rate | ACV $450,000 → **Pending Approval**, route RevOps + Finance + VP Sales, five audit rows |
| **FastScale AI** | Clay hiring signals, HubSpot meeting + emails, 3 pricing visits, 40% MoM usage growth | priority **87.0** → Tier 1 → one Salesforce Task created by Flow B, deduped on re-run |

`python -m src.main scenarios` prints all three. `docs/scenario_tests.md` is the walkthrough.

## How a quote is decided

```
quote request
  → quote_validator      structural rules, commitment must match list price unless custom pricing
  → pricing_engine       usage overage (custom rate replaces list rate) → gross → discount → net → ACV
  → approval_rules       thresholds from policy.yaml → status, ordered approvers, reasons
  → audit                one quotes row, ≥ 1 approval_audit rows (auto-approvals included)
  → Salesforce sync      Quote__c + Approval_Audit__c upserted by external ID
  → Flow A               emails Quote Owner + RevOps mailbox, stamps timestamps; no policy math
```

Approval matrix (generated from the policy file by `python -m src.main policy --render`):

| Rule | Route |
|---|---|
| Discount ≤ 10%, standard terms, ACV < $100K | Auto-approve |
| Discount 10–20% | Sales Manager |
| Discount > 20% | RevOps + Finance |
| ACV ≥ $100K | VP Sales |
| Custom pricing, commitment, or overage rate | RevOps |
| Payment terms other than Net 30 / Annual Prepaid | Finance |

## How an account is prioritized

```
priority = 0.40·intent + 0.30·usage + 0.20·engagement + 0.10·firmographic     (weights in policy.yaml)
Tier 1 ≥ 80 · Tier 2 ≥ 60 · Tier 3 otherwise
```

Each score carries a deterministic `scoring_reason`, for example: *Tier 1 because product usage grew 40% month-over-month, the account visited pricing pages 3 times, requested a demo, is hiring for 2 ML roles, and firmographic fit is high.* With `AI_ENABLED=true`, one Claude call per Tier 1 account drafts a narrative, a task description and an outbound email from those facts. It never changes a number.

## Quote-to-cash (v2, item 1)

Approved quotes are handed to a NetSuite-style ERP and reconciled. A person approves or rejects a pending quote in Salesforce (or via the `decide` command as a stand-in), Flow A stamps the approver and timestamp, the engine reads the decision back with a `HUMAN_DECISION` audit row, builds a sales-order payload with a monthly billing schedule, sends it to the mock ERP (in-process by default, or over HTTP with `ERP_URL`), and writes the order id and `Reconciled` status back to DuckDB and `Quote__c`.

```bash
python -m src.main decide --quote-id Q-00002 --decision Approved --approver "Jane Doe"
python -m src.main sync-approval-outcomes
python -m src.main erp-handoff
```

Salesforce is the system of record for human decisions: the quote sync never overwrites an Approved or Rejected status set there. Design: `docs/V2_DESIGN.md`.

## Repository layout

```
config/policy.yaml     single policy authority (thresholds, weights, tiers, SLA)
data/raw/              seeded CSVs: accounts, Clay-shaped enrichment, HubSpot-shaped engagement, signals, usage, products, quotes
sql/                   DDL, loads, scoring views, parameterized DQ checks, reporting views (Snowflake-style)
src/cpq/               validator, pricing engine, approval rules, audit persistence
src/scoring/           sub-scores, tiering, explanation, scoring runner
src/ingestion/         schema validation, raw load, HubSpot mapping
src/salesforce/        client protocol, mock (Flow A/B emulation), real client, sync, task and approval readback, ERP write-back
src/erp/               sales-order payload, NetSuite-style mock client (in-process or HTTP), handoff + reconciliation
erp/mock_server.py     standalone HTTP mock of the ERP sales-order API
src/ai/                optional drafter (one Claude call, template fallback)
src/monitoring/        JSON logging, integration log, DQ runner, alerts
src/main.py            CLI: init-db · load-raw · validate · score · evaluate · draft · research · sync · sync-task-outcomes · dq · run-all · scenarios
api/                   FastAPI, three routes
dashboard/app.py       Streamlit, three tabs
sfdx/                  deployable metadata: objects, fields, permission set, custom setting, two Flows
tests/                 66 tests incl. exact reproduction of the scenarios and the quote-to-cash path
docs/                  technical design, data dictionary, Salesforce mapping and setup, scenario tests, talk track
```

## Documentation

- [Technical design](docs/TECHNICAL_DESIGN.md) — architecture, HLD, LLD, decisions, roadmap
- [Data dictionary](docs/data_dictionary.md)
- [Approval matrix](docs/approval_matrix.md) (generated)
- [Salesforce mapping](docs/salesforce_mapping.md) and [setup](docs/salesforce_setup.md)


