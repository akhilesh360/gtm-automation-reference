"""CLI entry point.

  python -m src.main init-db | load-raw | validate | score | evaluate | draft | research --account-id ID
                     | sync | sync-task-outcomes | dq | run-all | demo | policy --render
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Optional

from src.config import PROJECT_ROOT, settings
from src.cpq.audit import persist_evaluation
from src.cpq.evaluate import evaluate_quote
from src.cpq.models import Product, QuoteRequest
from src.db import run_sql_file, session
from src.ingestion.load_raw import load_all
from src.ingestion.validate_schema import validate_raw_dir
from src.monitoring.alerts import summarize
from src.monitoring.logger import STATUS_FAILED_VALIDATION, get_logger, new_correlation_id, workflow_run
from src.monitoring.quality_checks import has_errors, run_checks
from src.policy import get_policy, render_approval_matrix
from src.salesforce.client import get_client
from src.salesforce.sync import create_quotes, sync_task_outcomes, upsert_accounts, upsert_scores
from src.scoring.run import score_all

log = get_logger()


# ---------------------------------------------------------------- stages
def stage_init_db(con, cid):
    run_sql_file(con, "01_create_tables.sql")  # DDL first: integration_log must exist before anything is logged
    with workflow_run(con, "init_db", cid):
        run_sql_file(con, "05_reporting_views.sql", {"pending_sla_days": get_policy().sla.pending_approval_days})
    print("DuckDB initialized:", settings.duckdb_file)


def stage_validate(con, cid) -> bool:
    issues = validate_raw_dir(settings.raw_dir)
    with workflow_run(con, "validate_schema", cid) as ctx:
        errors = [i for i in issues if i.severity == "error"]
        for i in issues:
            print(f"  [{i.severity.upper()}] {i.file}: {i.message}")
        if errors:
            ctx["failure_status"] = STATUS_FAILED_VALIDATION
            raise SystemExit(f"schema validation failed with {len(errors)} error(s)")
    print(f"Schema validation passed ({len(issues)} warning(s))")
    return True


def stage_load_raw(con, cid):
    with workflow_run(con, "load_raw", cid):
        counts = load_all(con)
    for k, v in counts.items():
        print(f"  {k:20s} {v}")


def stage_score(con, cid):
    policy = get_policy()
    with workflow_run(con, "score_accounts", cid):
        tiers = score_all(con, policy, cid)
    print("Scored accounts:", tiers)


def stage_evaluate(con, cid):
    policy = get_policy()
    products = {r[0]: Product(product_id=r[0], product_name=r[1], pricing_model=r[2], list_price_monthly=float(r[3]),
                              included_units=int(r[4]) if r[4] is not None else None,
                              overage_price_per_unit=float(r[5]) if r[5] is not None else None)
                for r in con.execute("SELECT * FROM products").fetchall()}
    rows = con.execute("SELECT * FROM quote_requests ORDER BY quote_id").fetchall()
    cols = [d[0] for d in con.description]
    summary = {"Auto-Approved": 0, "Pending Approval": 0, "Failed Validation": 0}
    with workflow_run(con, "evaluate_quotes", cid):
        for r in rows:
            d = dict(zip(cols, r))
            req = QuoteRequest(
                quote_id=d["quote_id"], account_id=d["account_id"], account_name=d["account_name"], product_id=d["product_id"],
                monthly_commitment=float(d["monthly_commitment"] or 0), quantity=int(d["quantity"] or 1),
                contract_term_months=int(d["contract_term_months"] or 0), discount_percent=float(d["discount_percent"] or 0),
                payment_terms=d["payment_terms"] or "", custom_pricing=bool(d["custom_pricing"]),
                forecasted_units=int(d["forecasted_units"]) if d["forecasted_units"] is not None else None,
                custom_overage_rate=float(d["custom_overage_rate"]) if d["custom_overage_rate"] is not None else None,
            )
            ev = evaluate_quote(req, products.get(req.product_id), policy)
            persist_evaluation(con, ev, policy, cid, requested_at=d["requested_at"])
            summary[ev.status] = summary.get(ev.status, 0) + 1
            log.info("quote evaluated", extra={"workflow": "evaluate_quotes", "record_type": "quote", "record_id": req.quote_id,
                                               "status": ev.status, "correlation_id": cid, "policy_version": policy.version,
                                               "extra": {"route": ev.decision.route}})
    print("Quotes evaluated:", summary)


def stage_draft(con, cid, limit: Optional[int] = None):
    from src.ai.run import draft_all
    with workflow_run(con, "draft", cid):
        counts = draft_all(con, limit=limit)
    print("Drafts:", counts, "(AI enabled)" if settings.ai_enabled else "(template mode)")


def stage_sync(con, cid):
    sf = get_client()
    with workflow_run(con, "sync_salesforce", cid):
        n_acc = upsert_accounts(con, sf, cid)
        n_scores = upsert_scores(con, sf, cid)
        n_quotes = create_quotes(con, sf, cid)
    print(f"Synced via {sf.name}: {n_acc} accounts, {n_scores} scores, {n_quotes} quotes (+ audit rows)")


def stage_sync_task_outcomes(con, cid):
    sf = get_client()
    n = sync_task_outcomes(con, sf, cid)
    print(f"Task outcomes read back: {n} task(s) now linked to Salesforce Task Ids")


def stage_dq(con, cid) -> bool:
    policy = get_policy()
    with workflow_run(con, "dq_checks", cid):
        run_id, results = run_checks(con, policy)
    for r in results:
        flag = "ERROR" if (r.severity == "error" and r.row_count) else "warn " if r.row_count else "ok   "
        print(f"  {flag} {r.check_name:32s} {r.row_count:4d}  {', '.join(r.sample_ids)}")
    print(summarize(con, results))
    return not has_errors(results)


def stage_report(con):
    print("\n=== Summary ===")
    for row in con.execute("SELECT * FROM v_cpq_summary").fetchall():
        print("CPQ:", row)
    print("Tiers:", con.execute("SELECT * FROM v_accounts_by_tier").fetchall())
    print("Dashboard: streamlit run dashboard/app.py")


def run_all(reset_mock: bool = True) -> int:
    cid = new_correlation_id()
    print("correlation_id:", cid)
    if reset_mock and not settings.sf_enabled and settings.mock_sf_file.exists():
        settings.mock_sf_file.unlink()
    with session() as con:
        stage_init_db(con, cid)
        stage_validate(con, cid)
        stage_load_raw(con, cid)
        stage_score(con, cid)
        stage_evaluate(con, cid)
        stage_draft(con, cid)
        stage_sync(con, cid)
        stage_sync_task_outcomes(con, cid)
        ok = stage_dq(con, cid)
        stage_report(con)
    return 0 if ok else 1


def demo():
    """Run the pipeline, then print the three scenarios."""
    run_all()
    with session() as con:
        print("\n=== Scenario 1: Alpha AI (standard startup quote) ===")
        _print_quote(con, "Q-00001")
        print("\n=== Scenario 2: EnterpriseGen (enterprise exception quote) ===")
        _print_quote(con, "Q-00002")
        print("\n=== Scenario 3: FastScale AI (high-intent account) ===")
        r = con.execute("SELECT priority_score, account_tier, intent_score, usage_score, engagement_score, firmographic_fit_score, "
                        "scoring_reason, task_description, draft_source FROM account_scores WHERE account_id = 'ACC-00003'").fetchone()
        print(f"  priority {r[0]}  {r[1]}  (intent {r[2]}, usage {r[3]}, engagement {r[4]}, fit {r[5]})")
        print(f"  reason: {r[6]}")
        print(f"  task description ({r[8]}): {r[7]}")
        t = con.execute("SELECT task_id, status, sf_task_id FROM sales_tasks WHERE account_id = 'ACC-00003' AND priority = 'High'").fetchall()
        print(f"  sales_tasks: {t}")


def _print_quote(con, quote_id):
    q = con.execute("SELECT account_name, product_id, monthly_commitment, contract_term_months, discount_percent, payment_terms, "
                    "overage_units, monthly_overage, gross_contract_value, discount_amount, net_contract_value, annual_contract_value, "
                    "approval_status, approval_route FROM quotes WHERE quote_id = ?", [quote_id]).fetchone()
    print(f"  {q[0]} | {q[1]} | ${q[2]:,.0f}/mo x {q[3]} mo | {q[4]}% | {q[5]} | overage {q[6]} units (${q[7] or 0:,.2f}/mo)")
    print(f"  gross ${q[8]:,.2f}  discount ${q[9]:,.2f}  net ${q[10]:,.2f}  ACV ${q[11]:,.2f}")
    print(f"  status: {q[12]}   route: {q[13] or '-'}")
    for a in con.execute("SELECT rule_triggered, required_approver, decision_reason FROM approval_audit WHERE quote_id = ? ORDER BY audit_id", [quote_id]).fetchall():
        print(f"    audit: {a[0]:18s} {str(a[1] or '-'):14s} {a[2]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gtm", description="GTM Revenue Operations Engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init-db", "load-raw", "validate", "score", "evaluate", "sync", "sync-task-outcomes", "dq", "run-all", "demo"):
        sub.add_parser(name)
    d = sub.add_parser("draft"); d.add_argument("--limit", type=int, default=None)
    r = sub.add_parser("research"); r.add_argument("--account-id", required=True)
    g = sub.add_parser("generate-data"); g.add_argument("--seed", type=int, default=None)
    pol = sub.add_parser("policy"); pol.add_argument("--render", action="store_true")
    args = p.parse_args(argv)

    if args.cmd == "run-all":
        return run_all()
    if args.cmd == "demo":
        demo(); return 0
    if args.cmd == "generate-data":
        from scripts.generate_mock_data import generate
        print(generate(seed=args.seed)); return 0
    if args.cmd == "policy":
        pol_obj = get_policy()
        if args.render:
            out = PROJECT_ROOT / "docs" / "approval_matrix.md"
            out.write_text(render_approval_matrix(pol_obj), encoding="utf-8")
            print("wrote", out)
        else:
            print(pol_obj.model_dump_json(indent=2))
        return 0

    cid = new_correlation_id()
    with session() as con:
        if args.cmd == "init-db": stage_init_db(con, cid)
        elif args.cmd == "validate": stage_validate(con, cid)
        elif args.cmd == "load-raw": stage_load_raw(con, cid)
        elif args.cmd == "score": stage_score(con, cid)
        elif args.cmd == "evaluate": stage_evaluate(con, cid)
        elif args.cmd == "draft": stage_draft(con, cid, limit=args.limit)
        elif args.cmd == "research":
            from src.ai.run import research_one
            res = research_one(con, args.account_id)
            if res is None:
                print("account not found or not scored yet:", args.account_id); return 1
            print(f"[{res.source}] narrative:\n{res.draft.narrative}\n\ntask description:\n{res.draft.task_description}\n\noutbound draft:\n{res.draft.outbound_draft}")
        elif args.cmd == "sync": stage_sync(con, cid)
        elif args.cmd == "sync-task-outcomes": stage_sync_task_outcomes(con, cid)
        elif args.cmd == "dq": return 0 if stage_dq(con, cid) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
