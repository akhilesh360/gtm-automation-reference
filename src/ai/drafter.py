"""Optional AI-assisted drafting. One Claude call per Tier 1 account; deterministic template otherwise.

The model never decides anything: scores, tier and scoring_reason are inputs. Any failure -> template.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional

from pydantic import BaseModel, ValidationError as PydanticValidationError

from src.config import settings
from src.monitoring.logger import get_logger
from src.ai.prompts import SYSTEM_PROMPT, user_prompt

log = get_logger()


@dataclass
class DraftFacts:
    account_id: str
    account_name: str
    account_owner: Optional[str]
    account_tier: str
    priority_score: float
    intent_score: float
    usage_score: float
    engagement_score: float
    firmographic_fit_score: float
    scoring_reason: str
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    funding_stage: Optional[str] = None
    mom_growth_pct: Optional[float] = None
    pricing_page_visits: float = 0
    demo_requests: float = 0
    ml_job_postings: float = 0
    email_engagements: float = 0
    company_summary: Optional[str] = None
    personalization_hook: Optional[str] = None
    tech_stack: Optional[str] = None
    open_quotes: Optional[list[dict]] = None

    def as_json(self) -> str:
        return json.dumps(asdict(self), default=str, sort_keys=True)


class Draft(BaseModel):
    narrative: str
    task_description: str
    outbound_draft: str


@dataclass
class DraftResult:
    draft: Draft
    source: str  # "template" | "claude"


def template_draft(f: DraftFacts) -> Draft:
    owner = f.account_owner or "the account owner"
    first = f.account_name
    hook = f.personalization_hook or f"your {f.industry or 'AI'} roadmap"
    signals = []
    if f.mom_growth_pct and f.mom_growth_pct >= 15:
        signals.append(f"usage up {f.mom_growth_pct:.0f}% month over month")
    if f.pricing_page_visits:
        signals.append(f"{int(f.pricing_page_visits)} pricing-page visit{'s' if f.pricing_page_visits != 1 else ''}")
    if f.demo_requests:
        signals.append("a demo request")
    if f.ml_job_postings:
        signals.append(f"{int(f.ml_job_postings)} open ML role{'s' if f.ml_job_postings != 1 else ''}")
    signal_text = ", ".join(signals) if signals else "steady engagement"
    narrative = (f"{first} is {f.account_tier} with a priority score of {f.priority_score:.1f}. "
                 f"{f.scoring_reason} Recent signals: {signal_text}.")
    task = (f"Reach out to {first} this week to discuss expansion. Reference {signal_text} and confirm "
            f"budget owner and timeline.")
    outbound = (f"Hi team at {first},\n\n"
                f"I noticed {hook}. Teams at a similar stage usually hit the point where {signal_text} means it is "
                f"time to lock in capacity and pricing before the next growth step.\n\n"
                f"Would it be useful to compare notes on how other {f.industry or 'AI'} teams structured their commitments? "
                f"Happy to share benchmarks. If it is easier, reply with a time and I will send an invite.\n\n"
                f"Best,\n{owner}")
    return Draft(narrative=narrative, task_description=task, outbound_draft=outbound)


def _claude_draft(f: DraftFacts) -> Draft:
    import anthropic  # imported lazily so the template path has no dependency

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60.0)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt(f.as_json())}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model refused the request")
    text = next((b.text for b in response.content if b.type == "text"), "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model response")
    return Draft.model_validate_json(text[start:end + 1])


def draft(f: DraftFacts) -> DraftResult:
    if not (settings.ai_enabled and settings.anthropic_api_key):
        return DraftResult(template_draft(f), "template")
    try:
        return DraftResult(_claude_draft(f), "claude")
    except (PydanticValidationError, ValueError, RuntimeError) as e:
        log.warning("AI draft invalid, using template", extra={"record_id": f.account_id, "extra": str(e)})
    except Exception as e:  # noqa: BLE001  (network, auth, rate limit, ...)
        log.warning("AI draft failed, using template", extra={"record_id": f.account_id, "extra": str(e)})
    return DraftResult(template_draft(f), "template")
