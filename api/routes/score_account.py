from fastapi import APIRouter, HTTPException

from api.models import ScoreAccountRequest, ScoreAccountResponse
from src.db import session
from src.policy import get_policy
from src.scoring.account_scoring import SubScores, fetch_facts, priority_score, sub_scores
from src.scoring.explain_score import explain
from src.scoring.tiering import assign_tier, tier_action

router = APIRouter()


@router.post("/score-account", response_model=ScoreAccountResponse, tags=["business"])
def score_account(req: ScoreAccountRequest) -> ScoreAccountResponse:
    policy = get_policy()
    if req.account_id:
        with session() as con:
            facts = next((f for f in fetch_facts(con, policy) if f.account_id == req.account_id), None)
        if facts is None:
            raise HTTPException(status_code=404, detail=f"account {req.account_id} not found")
        s = sub_scores(facts)
        p = priority_score(s, policy)
        tier = assign_tier(p, policy)
        reason = explain(facts, s, tier)
        name = facts.account_name
    else:
        missing = [k for k in ("intent_score", "usage_score", "engagement_score", "firmographic_fit_score") if getattr(req, k) is None]
        if missing:
            raise HTTPException(status_code=422, detail=f"provide account_id or all of: {missing}")
        s = SubScores(req.intent_score, req.engagement_score, req.usage_score, req.firmographic_fit_score)
        p = priority_score(s, policy)
        tier = assign_tier(p, policy)
        reason = f"{tier} from inline sub-scores (intent {s.intent}, usage {s.usage}, engagement {s.engagement}, fit {s.firmographic})."
        name = req.account_name
    return ScoreAccountResponse(
        account_id=req.account_id, account_name=name,
        sub_scores={"intent": s.intent, "usage": s.usage, "engagement": s.engagement, "firmographic": s.firmographic},
        priority_score=p, account_tier=tier, scoring_reason=reason, action=tier_action(tier), policy_version=policy.version,
    )
