"""v2 item 2: opportunities, funnel, bottleneck, conversion by tier."""
import duckdb


def _con(pipeline_db):
    return duckdb.connect(str(pipeline_db), read_only=True)


def test_funnel_is_monotonic_and_starts_with_all_opportunities(pipeline_db):
    con = _con(pipeline_db)
    rows = con.execute("SELECT stage, opportunities, step_conversion_pct FROM v_funnel ORDER BY stage_order").fetchall()
    total = con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    assert rows[0][0] == "Prospecting" and rows[0][1] == total and rows[0][2] is None
    counts = [r[1] for r in rows]
    assert counts == sorted(counts, reverse=True)
    assert all(0 < r[2] <= 100 for r in rows[1:])


def test_seeded_bottleneck_is_proposal_to_negotiation(pipeline_db):
    con = _con(pipeline_db)
    b = con.execute("SELECT from_stage, to_stage, step_conversion_pct FROM v_bottleneck WHERE bottleneck").fetchall()
    assert len(b) == 1 and (b[0][0], b[0][1]) == ("Proposal", "Negotiation")
    others = con.execute("SELECT MIN(step_conversion_pct) FROM v_bottleneck WHERE NOT bottleneck").fetchone()[0]
    assert b[0][2] <= others


def test_win_rate_ordered_by_tier(pipeline_db):
    con = _con(pipeline_db)
    rows = dict((r[0], r[1]) for r in con.execute("SELECT source_tier, win_rate_pct FROM v_conversion_by_tier").fetchall())
    assert rows["Tier 1"] > rows["Tier 2"] > rows["Tier 3"]


def test_stage_cycle_has_proposal_as_longest(pipeline_db):
    con = _con(pipeline_db)
    rows = dict((r[0], float(r[1])) for r in con.execute("SELECT stage, median_days FROM v_stage_cycle").fetchall())
    assert max(rows, key=rows.get) == "Proposal"


def test_seeded_opportunity_defects_are_caught(pipeline_db):
    con = _con(pipeline_db)
    rows = dict(con.execute("SELECT check_name, row_count FROM v_dq_latest").fetchall())
    assert rows["opportunities_without_stage_history"] == 1
    assert rows["closed_won_missing_amount"] == 1


def test_opportunities_synced_to_salesforce_with_mapped_stages(pipeline_db):
    from src.salesforce.client import MockSalesforceClient
    sf = MockSalesforceClient()
    opps = sf.query("SELECT StageName, Source_Tier__c FROM Opportunity")
    con = _con(pipeline_db)
    assert len(opps) == con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    assert {o["StageName"] for o in opps} <= {"Prospecting", "Qualification", "Proposal/Price Quote", "Negotiation/Review", "Closed Won", "Closed Lost"}
    assert con.execute("SELECT COUNT(*) FROM opportunities WHERE sf_opportunity_id IS NULL").fetchone()[0] == 0
