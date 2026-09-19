"""The three test scenarios must reproduce the design doc exactly, end to end, with no env vars set."""
import duckdb


def _con(pipeline_db):
    return duckdb.connect(str(pipeline_db), read_only=True)


def test_scenario_1_alpha_ai_auto_approved(pipeline_db):
    con = _con(pipeline_db)
    q = con.execute("SELECT gross_contract_value, discount_amount, net_contract_value, annual_contract_value, approval_status, approval_route "
                    "FROM quotes WHERE quote_id = 'Q-00001'").fetchone()
    assert [float(x) for x in q[:4]] == [60000, 3000, 57000, 57000]
    assert q[4] == "Auto-Approved" and q[5] == ""
    audit = con.execute("SELECT rule_triggered, required_approver FROM approval_audit WHERE quote_id = 'Q-00001'").fetchall()
    assert audit == [("STANDARD_POLICY", None)]


def test_scenario_2_enterprisegen_routes_with_five_audit_rows(pipeline_db):
    con = _con(pipeline_db)
    q = con.execute("SELECT overage_units, monthly_overage, gross_contract_value, discount_amount, net_contract_value, annual_contract_value, "
                    "approval_status, approval_route FROM quotes WHERE quote_id = 'Q-00002'").fetchone()
    assert q[0] == 0 and float(q[1]) == 0
    assert [float(x) for x in q[2:6]] == [600000, 150000, 450000, 450000]
    # policy decision is Pending Approval; test_quote_to_cash may already have applied the human approval (v2)
    assert q[6] in ("Pending Approval", "Approved") and q[7] == "RevOps, Finance, VP Sales"
    rules = [r[0] for r in con.execute("SELECT rule_triggered FROM approval_audit WHERE quote_id = 'Q-00002' "
                                        "AND rule_triggered <> 'HUMAN_DECISION' ORDER BY audit_id").fetchall()]
    assert rules == ["DISCOUNT_GT_20", "DISCOUNT_GT_20", "ACV_GTE_100K", "NONSTANDARD_TERMS", "CUSTOM_PRICING"]


def test_scenario_3_fastscale_is_tier1_with_one_task(pipeline_db):
    con = _con(pipeline_db)
    s = con.execute("SELECT intent_score, usage_score, engagement_score, firmographic_fit_score, priority_score, account_tier, "
                    "scoring_reason, task_description, draft_source FROM account_scores WHERE account_id = 'ACC-00003'").fetchone()
    assert [float(x) for x in s[:5]] == [90, 90, 80, 80, 87.0]
    assert s[5] == "Tier 1" and s[6].startswith("Tier 1 because") and "40%" in s[6]
    assert s[7] and s[8] == "template"
    tasks = con.execute("SELECT status, sf_task_id FROM sales_tasks WHERE account_id = 'ACC-00003' AND priority = 'High'").fetchall()
    assert len(tasks) == 1 and tasks[0][0] == "open" and tasks[0][1]


def test_tier1_without_open_task_check_passes_after_outcome_sync(pipeline_db):
    con = _con(pipeline_db)
    r = con.execute("SELECT row_count FROM v_dq_latest WHERE check_name = 'tier1_without_open_task'").fetchone()
    assert r[0] == 0


def test_seeded_defects_are_caught(pipeline_db):
    con = _con(pipeline_db)
    rows = dict(con.execute("SELECT check_name, row_count FROM v_dq_latest").fetchall())
    assert rows["duplicate_account_domains"] >= 2
    assert rows["accounts_without_owner"] >= 2
    assert rows["invalid_discounts"] >= 1
    assert rows["accounts_without_domain"] >= 2
