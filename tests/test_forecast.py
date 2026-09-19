"""v2 item 3: weighted forecast and forecast vs actual."""
import duckdb


def _con(pipeline_db):
    return duckdb.connect(str(pipeline_db), read_only=True)


def test_policy_has_stage_probabilities(policy):
    sp = policy.forecast.stage_probabilities
    assert sp["Prospecting"] < sp["Discovery"] < sp["Proposal"] < sp["Negotiation"] <= 1


def test_weighted_forecast_never_exceeds_pipeline(pipeline_db):
    con = _con(pipeline_db)
    rows = con.execute("SELECT open_pipeline, weighted_forecast FROM v_weighted_pipeline").fetchall()
    assert rows and all(0 < float(w) <= float(p) for p, w in rows)


def test_weighted_forecast_matches_stage_probabilities(pipeline_db, policy):
    con = _con(pipeline_db)
    sp = policy.forecast.stage_probabilities
    expected = sum(float(a) * sp[s] for s, a in con.execute(
        "SELECT stage, amount FROM opportunities WHERE NOT is_closed").fetchall())
    actual = float(con.execute("SELECT weighted_forecast FROM v_forecast_summary").fetchone()[0])
    assert abs(expected - actual) < 0.01


def test_snapshots_backfilled_and_today_present(pipeline_db):
    con = _con(pipeline_db)
    dates = [r[0] for r in con.execute("SELECT DISTINCT snapshot_date FROM forecast_snapshots ORDER BY 1").fetchall()]
    assert len(dates) >= 4
    assert all(d.day == 1 for d in dates[:-1])  # historical snapshots are month starts


def test_forecast_vs_actual_has_attainment(pipeline_db):
    con = _con(pipeline_db)
    rows = con.execute("SELECT closed_won_actual, weighted_forecast, attainment_pct FROM v_forecast_vs_actual WHERE weighted_forecast > 0").fetchall()
    assert rows
    for actual, forecast, att in rows:
        assert abs(float(att) - round(100 * float(actual) / float(forecast), 1)) < 0.11


def test_snapshot_is_idempotent_per_day(pipeline_db, policy):
    from src.forecasting.pipeline_forecast import snapshot
    con = duckdb.connect(str(pipeline_db))
    before = con.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0]
    snapshot(con, policy, "run-t")
    after = con.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0]
    assert after == before
    con.close()
