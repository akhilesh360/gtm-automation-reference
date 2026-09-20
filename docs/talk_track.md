# Talk track

Short answers to the questions this project is likely to prompt.

**Status?**
v1 is complete. I tested the seeded scenarios, deployed the Salesforce metadata to a Developer Org, verified the Flow behavior, and confirmed the offline and Salesforce-connected modes.

**What is this?**
A Salesforce-centered reference implementation of CPQ-style pricing governance, discount approvals, signal-based account prioritization, CRM data-quality controls and RevOps reporting. Deterministic Python and SQL make every decision; AI only drafts prose; Salesforce executes CRM actions.

**Is it Salesforce CPQ or Revenue Cloud?**
No. It uses custom objects to demonstrate commercial-policy and quote-governance patterns. It does not model the Revenue Cloud catalog, price books, amendments, renewals, orders, assets, billing schedules or subscription lifecycle. It is the governance layer you would put around such a system.

**Where does policy live?**
`config/policy.yaml`, versioned and validated on load. Python reads it, SQL checks receive thresholds as parameters, and Flows contain none. The approval matrix doc is generated from it, so documentation cannot drift.

**Why doesn't the Flow re-check the discount?**
Two engines disagree eventually. Python decides once, writes status, route and audit rows, and stamps the policy version on the record. Flow A only notifies and timestamps; Flow B only creates Tasks and prevents duplicates.

**How is usage-based pricing handled?**
Commitment plus overage: `max(forecast − included, 0) × rate`, where a custom overage rate replaces the list rate and independently triggers RevOps review. The monthly total becomes the effective list price before discount, then gross, discount, net and ACV follow.

**What happens on an approval?**
v1 evaluates policy, routes exceptions, writes audit rows, and Flow A emails the Quote Owner plus a RevOps test mailbox with the route. Human approve/reject capture and role-to-user routing are v2.

**Where does Clay fit?**
Upstream only: firmographics, hiring signals, research summary and a personalization hook. It feeds scoring and outbound drafts. It never touches pricing, approvals, quotes or CRM source-of-truth records.

**How do you keep data quality honest?**
Schema validation before load, dedupe on load, a quote validator that rejects bad requests before routing, nine SQL checks parameterized by policy, a `dq_results` table and an exit code that fails CI on any error-severity check.

**How would you trace a failure?**
Every run has a correlation ID that appears in the JSON log, `integration_log`, and `Integration_Log__c`. Sync calls retry three times with backoff and record `RETRYING` then `FAILED_API`.

**How does an approved quote reach finance?**
A person approves in Salesforce; Flow A stamps approver and time. The engine reads that back, adds a human-decision audit row, and builds a sales order with a monthly billing schedule that sums to the net value. A NetSuite-style mock accepts it and returns an order id; the engine checks the accepted total against the quote, marks it Reconciled, and writes the order id back to the quote in Salesforce. The mock is in-process by default or an HTTP service, so a real NetSuite adapter is a drop-in replacement.

**Where do deals stall?**
Every stage transition is recorded with days in stage. The funnel view computes step conversion and flags the lowest step as the bottleneck; in the seeded data that is Proposal to Negotiation. Conversion is broken out by the tier the account had when the deal was created, so the scoring model's value shows up as a win-rate gap between tiers.

**How do you forecast?**
Stage probabilities sit in the same policy file as the discount thresholds, so finance can see and version them. Open deals are weighted by close month and tier, every run stores a dated snapshot, and closed months are compared with the forecast that stood on the first of that month. On the seeded data Tier 1 over-attains and Tier 3 under-attains, which is exactly the argument for tier-specific probabilities as the next step.

**What happens to Tier 2 accounts?**
They are enrolled in a standard outbound sequence with the drafted first touch attached, one active enrollment per account, so outbound volume by tier is a number on the dashboard rather than an intention. Tier 1 gets executive outreach plus the Salesforce Task; Tier 3 stays in nurture.

**What's next?**
Sequence management, live Clay and HubSpot connectors, and a bounded Claude research loop.
