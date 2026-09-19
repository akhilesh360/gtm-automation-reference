# Approval matrix (policy version 2026.09)

Generated from `config/policy.yaml` by `python -m src.main policy --render`. Do not edit by hand.

| Rule | Route |
|---|---|
| Discount 0–10%, standard terms (Net 30 / Annual Prepaid), ACV < $100,000 | Auto-approve, `STANDARD_POLICY` audit row |
| Discount 10–20% | Sales Manager |
| Discount > 20% | RevOps + Finance |
| ACV ≥ $100,000 | VP Sales |
| Custom pricing, custom commitment, or custom overage rate | RevOps |
| Payment terms other than Net 30 / Annual Prepaid | Finance |

Approver order on a route: Sales Manager, RevOps, Finance, VP Sales.
Pending-approval SLA: 2 days.
