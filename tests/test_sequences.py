"""v2 item 4: outbound sequence enrollment with dedupe."""
import duckdb

from src.outbound.sequences import enroll_accounts


def _con(pipeline_db, ro=True):
    return duckdb.connect(str(pipeline_db), read_only=ro)


def test_tier1_and_tier2_enrolled_tier3_not(pipeline_db):
    con = _con(pipeline_db)
    rows = con.execute("SELECT s.account_tier, e.sequence_name, COUNT(*) FROM sequence_enrollments e "
                       "JOIN account_scores s ON s.account_id = e.account_id GROUP BY 1, 2").fetchall()
    tiers = {r[0]: r[1] for r in rows}
    assert tiers == {"Tier 1": "tier1_exec_outreach", "Tier 2": "tier2_outbound"}
    enrolled = con.execute("SELECT COUNT(*) FROM sequence_enrollments").fetchone()[0]
    eligible = con.execute("SELECT COUNT(*) FROM account_scores WHERE account_tier IN ('Tier 1','Tier 2')").fetchone()[0]
    assert enrolled == eligible


def test_fastscale_enrolled_in_exec_outreach_with_draft(pipeline_db):
    con = _con(pipeline_db)
    r = con.execute("SELECT sequence_name, status, first_touch_draft FROM sequence_enrollments WHERE account_id = 'ACC-00003'").fetchone()
    assert r[0] == "tier1_exec_outreach" and r[1] in ("active", "replied") and "FastScale AI" in r[2]


def test_re_enrollment_is_idempotent(pipeline_db, policy):
    con = _con(pipeline_db, ro=False)
    before = con.execute("SELECT COUNT(*) FROM sequence_enrollments").fetchone()[0]
    counts = enroll_accounts(con, policy, "run-t")
    after = con.execute("SELECT COUNT(*) FROM sequence_enrollments").fetchone()[0]
    assert counts["enrolled"] == 0 and counts["already_active"] == before and after == before
    con.close()


def test_no_duplicate_active_enrollments_and_reply_rate_reasonable(pipeline_db):
    con = _con(pipeline_db)
    rows = dict(con.execute("SELECT check_name, row_count FROM v_dq_latest").fetchall())
    assert rows["duplicate_active_enrollments"] == 0 and rows["tier2_without_enrollment"] == 0
    rate = con.execute("SELECT 100.0 * SUM(replied) / SUM(enrolled) FROM v_sequence_summary").fetchone()[0]
    assert 5 <= float(rate) <= 60
