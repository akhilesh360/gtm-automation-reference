from src.ai import drafter
from src.ai.drafter import DraftFacts, draft, template_draft


def _facts():
    return DraftFacts(account_id="ACC-00003", account_name="FastScale AI", account_owner="Elena", account_tier="Tier 1",
                      priority_score=87.0, intent_score=90, usage_score=90, engagement_score=80, firmographic_fit_score=80,
                      scoring_reason="Tier 1 because usage grew 40%.", industry="AI/ML", mom_growth_pct=40, pricing_page_visits=3,
                      demo_requests=1, ml_job_postings=2, personalization_hook="your push into inference")


def test_template_path_when_ai_disabled():
    res = draft(_facts())
    assert res.source == "template"
    assert "FastScale AI" in res.draft.narrative and res.draft.task_description and res.draft.outbound_draft


def test_template_never_changes_numbers():
    d = template_draft(_facts())
    assert "87.0" in d.narrative and "Tier 1" in d.narrative


def test_falls_back_to_template_when_model_call_fails(monkeypatch):
    monkeypatch.setattr(drafter.settings, "ai_enabled", True)
    monkeypatch.setattr(drafter.settings, "anthropic_api_key", "test-key")

    def boom(f):
        raise RuntimeError("network down")
    monkeypatch.setattr(drafter, "_claude_draft", boom)
    res = draft(_facts())
    assert res.source == "template"


def test_uses_model_output_when_valid(monkeypatch):
    monkeypatch.setattr(drafter.settings, "ai_enabled", True)
    monkeypatch.setattr(drafter.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(drafter, "_claude_draft",
                        lambda f: drafter.Draft(narrative="n", task_description="t", outbound_draft="o"))
    res = draft(_facts())
    assert res.source == "claude" and res.draft.narrative == "n"
