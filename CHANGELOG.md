# Changelog

## v2.3 — Weighted forecast and forecast vs actual
- Stage probabilities in `config/policy.yaml`, passed to SQL as parameters
- Weighted pipeline by close month and tier; dated `forecast_snapshots` with six months of history reconstructed from stage transitions
- Forecast-vs-actual and attainment views; forecast section on the Pipeline dashboard tab

## v2.2 — Pipeline funnel and bottleneck view
- Seeded opportunities with stage history correlated to account tier
- Funnel, bottleneck, days-in-stage, conversion-by-tier and open-pipeline SQL views
- Pipeline dashboard tab; opportunities synced to the Salesforce `Opportunity` object with mapped stages
- Two data-quality checks for opportunity integrity

## v2.1 — Quote-to-cash handoff
- Human approve/reject captured in Salesforce (Flow A stamps approver and time) and read back with a `HUMAN_DECISION` audit row
- Sales-order payload with billing schedule sent to a NetSuite-style mock ERP (in-process or HTTP); reconciliation written back to DuckDB and `Quote__c`
- Quote sync never overwrites a human decision recorded in Salesforce

## v1.0 — Reference implementation
- Commercial policy in one versioned file (`config/policy.yaml`); Python decides, Salesforce Flow executes
- CPQ-style pricing (subscription and usage with overage), validation, approval routing, audit trail
- Signal-based account scoring with deterministic explanations; Clay-shaped and HubSpot-shaped CSV inputs
- Mock and real Salesforce clients; deployable SFDX package with two orchestration-only Flows
- Optional AI-assisted drafting with template fallback
- Data-quality checks, JSON logging with correlation IDs, FastAPI service, Streamlit dashboard
- Verified offline and against a Salesforce Developer Edition org
