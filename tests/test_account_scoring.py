from src.scoring.account_scoring import ScoreFacts, priority_score, sub_scores
from src.scoring.explain_score import explain
from src.scoring.tiering import assign_tier


def _facts(**kw):
    base = dict(account_id="ACC-X", account_name="X", industry="AI/ML", employee_count=320, funding_stage="Series B",
                account_owner="O", pricing_page_visits=0, demo_requests=0, ml_job_postings=0, funding_events=0, oss_interest=0,
                website_visits=0, email_engagements=0, mom_growth_pct=0, active_users=0, last_signal_at=None)
    base.update(kw)
    return ScoreFacts(**base)


def test_fastscale_subscores_and_priority(policy):
    f = _facts(employee_count=3200, pricing_page_visits=3, demo_requests=1, ml_job_postings=2, website_visits=15,
               email_engagements=5, mom_growth_pct=40, active_users=260)
    s = sub_scores(f)
    assert (s.intent, s.usage, s.engagement, s.firmographic) == (90, 90, 80, 80)
    assert priority_score(s, policy) == 87.0
    assert assign_tier(87.0, policy) == "Tier 1"


def test_subscores_clamped_to_100(policy):
    f = _facts(demo_requests=5, pricing_page_visits=50, website_visits=999, email_engagements=999, mom_growth_pct=500, active_users=10000)
    s = sub_scores(f)
    assert s.intent == 100 and s.engagement == 100 and s.usage == 100


def test_tier_boundaries(policy):
    assert assign_tier(80, policy) == "Tier 1"
    assert assign_tier(79.99, policy) == "Tier 2"
    assert assign_tier(60, policy) == "Tier 2"
    assert assign_tier(59.99, policy) == "Tier 3"


def test_explanation_is_deterministic_and_mentions_drivers(policy):
    f = _facts(pricing_page_visits=3, mom_growth_pct=42)
    s = sub_scores(f)
    text = explain(f, s, "Tier 2")
    assert text.startswith("Tier 2 because") and "42%" in text and "pricing pages 3 times" in text
    assert explain(f, s, "Tier 2") == text
