import duckdb

from src.db import run_sql_file
from src.monitoring.quality_checks import has_errors, run_checks


def test_checks_run_on_empty_db_and_report_zero(policy):
    con = duckdb.connect(":memory:")
    run_sql_file(con, "01_create_tables.sql")
    run_id, results = run_checks(con, policy)
    assert run_id.startswith("DQ-") and len(results) == 15
    assert all(r.row_count == 0 for r in results) and not has_errors(results)


def test_sla_threshold_comes_from_policy(policy):
    con = duckdb.connect(":memory:")
    run_sql_file(con, "01_create_tables.sql")
    con.execute("INSERT INTO quotes (quote_id, account_id, product_id, approval_status, created_at) VALUES "
                "('Q-OLD','A','P','Pending Approval', CURRENT_TIMESTAMP - INTERVAL 3 DAY), "
                "('Q-NEW','A','P','Pending Approval', CURRENT_TIMESTAMP - INTERVAL 1 DAY)")
    _, results = run_checks(con, policy)
    sla = next(r for r in results if r.check_name == "quotes_pending_beyond_sla")
    assert sla.row_count == 1 and sla.sample_ids == ["Q-OLD"]
