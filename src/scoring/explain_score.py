"""Deterministic, human-readable explanation of a score. Never overwritten by AI."""
from __future__ import annotations

from src.scoring.account_scoring import ScoreFacts, SubScores


def explain(f: ScoreFacts, s: SubScores, tier: str) -> str:
    parts: list[str] = []
    if f.mom_growth_pct is not None and f.mom_growth_pct >= 15:
        parts.append(f"product usage grew {f.mom_growth_pct:.0f}% month-over-month")
    if f.pricing_page_visits >= 1:
        n = int(f.pricing_page_visits)
        parts.append(f"the account visited pricing pages {n} time{'s' if n != 1 else ''}")
    if f.demo_requests >= 1:
        parts.append("requested a demo")
    if f.ml_job_postings >= 1:
        parts.append(f"is hiring for {int(f.ml_job_postings)} ML role{'s' if f.ml_job_postings != 1 else ''}")
    if f.funding_events >= 1:
        parts.append("announced new funding")
    if f.email_engagements >= 3:
        parts.append(f"engaged with {int(f.email_engagements)} marketing emails")
    fit_word = "high" if s.firmographic >= 70 else "moderate" if s.firmographic >= 45 else "low"
    firm = f"firmographic fit is {fit_word}"
    if f.funding_stage or f.industry or f.employee_count:
        desc = " ".join(x for x in [f.funding_stage, f.industry] if x)
        emp = f", {f.employee_count:,} employees" if f.employee_count else ""
        firm += f" ({desc} company{emp})"
    parts.append(firm)
    if len(parts) == 1:
        body = parts[0]
    else:
        body = ", ".join(parts[:-1]) + ", and " + parts[-1]
    return f"{tier} because {body}."
