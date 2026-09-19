# Demo script (about 8 minutes)

## Setup (once)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.main demo
```

No `.env` is needed. Salesforce and the AI drafter are off; everything runs against DuckDB and the mock Salesforce client.

## 1. The policy is one file (30s)

Open `config/policy.yaml`. Every threshold the demo uses lives here: discount limits, the $100K VP threshold, standard payment terms, approver order, the pending-approval SLA, scoring weights and tier cutoffs. `docs/approval_matrix.md` is generated from it.

> "I centralized commercial-policy decisions in a versioned config to avoid policy drift. Salesforce Flow handles workflow execution and CRM actions after the decision is written back."

## 2. Scenario 1 — Alpha AI, standard quote (1 min)

From the `demo` output: Starter API Commitment, $5,000/month, 12 months, 5%, Net 30.

- Gross $60,000 → discount $3,000 → net $57,000 → ACV $57,000
- **Auto-Approved**, exactly one audit row `STANDARD_POLICY` with no approver

> "Every decision gets an audit row, including auto-approvals, so the trail is complete."

## 3. Scenario 2 — EnterpriseGen, exception quote (2 min)

Enterprise Platform, $50,000/month, 12 months, 25%, Net 60, 45M forecasted units against a 50M allowance, custom overage rate.

- Overage: 0 units, $0 (under the allowance), so gross stays $600,000 → net $450,000 → ACV $450,000
- **Pending Approval**, route `RevOps, Finance, VP Sales`
- Five audit rows: discount > 20% (RevOps, Finance), ACV ≥ $100K (VP Sales), nonstandard terms (Finance), custom pricing (RevOps)

> "A custom overage rate replaces the list rate for pricing and independently triggers RevOps review, even when no overage is forecasted."

## 4. Scenario 3 — FastScale AI, high-intent account (2 min)

Signals from Clay (2 open ML roles), HubSpot (meeting booked, 5 email engagements), web analytics (3 pricing-page visits, 15 site visits) and product telemetry (40% MoM growth).

- Sub-scores 90 / 90 / 80 / 80 → priority **87.0** → Tier 1
- `scoring_reason` is deterministic text; the task description is a template (or a Claude draft with `AI_ENABLED=true`)
- Python wrote a `planned` task row and synced `Account_Score__c`; the mock Flow B created one Salesforce Task; `sync-task-outcomes` linked it back (`status = open`, `sf_task_id` set)
- Re-run `python -m src.main run-all`: still one Task

> "Python owns decisioning; Salesforce Flow owns CRM-native task creation and duplicate prevention."

## 5. Data quality and observability (1.5 min)

The `dq` section of the output shows the seeded defects being caught: duplicate domains, missing owners, an invalid discount, stale pending quotes, accounts with signals but no enrichment. `tier1_without_open_task` is 0 because outcome sync runs before the checks.

```bash
tail -5 logs/gtm_automation.log
```

Every line carries a `correlation_id` and status; the same IDs are in `integration_log` and mirrored to `Integration_Log__c` when Salesforce is on.

## 6. Dashboard and API (1 min)

```bash
streamlit run dashboard/app.py
uvicorn api.app:app --reload   # then open http://127.0.0.1:8000/docs
```

Three tabs: CPQ Operations, Account Prioritization, Data Quality. Three API routes: `/health`, `/score-account`, `/evaluate-quote`.

## Optional: Claude drafting

```bash
AI_ENABLED=true ANTHROPIC_API_KEY=sk-... python -m src.main research --account-id ACC-00003
```

Prints a narrative, task description and outbound draft; `draft_source` becomes `claude`. Scores and tier are unchanged.
