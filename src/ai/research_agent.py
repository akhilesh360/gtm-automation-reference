"""Bounded AI-assisted account research (v2). One model, five read-only tools, at most MAX_TOOL_CALLS calls and a
wall-clock budget. Output is validated; any failure falls back to the deterministic template. The agent never
changes a score, tier, price or approval; it reads them.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from src.ai.drafter import template_draft
from src.ai.run import _facts_for
from src.ai.tools import TOOL_SCHEMAS, run_tool
from src.config import settings
from src.monitoring.logger import STATUS_SUCCESS, get_logger, write_integration_log

log = get_logger()
MAX_TOOL_CALLS = 6
TIME_BUDGET_SECONDS = 20.0

SYSTEM = """You are a revenue-operations research assistant. Use the tools to read what the system already knows about ONE
account, then write for an account executive with 30 seconds. Never recompute or dispute the numbers, tier or scoring
reason the tools return; they are final. Do not invent facts. When you have enough, respond with a single JSON object
and nothing else, with keys:
  "brief": 5-8 sentences on why this account matters now, what they are doing, and what to lead with;
  "outbound_draft": a 4-6 sentence first-touch email body (no subject, no signature) using the personalization hook;
  "talking_points": a list of 3-5 short strings.
Call get_account first. Call other tools only if they would change what you write."""


class Research(BaseModel):
    brief: str
    outbound_draft: str
    talking_points: list[str]


@dataclass
class ResearchResult:
    research: Research
    source: str      # "template" | "claude"
    tool_calls: int


def template_research(con: duckdb.DuckDBPyConnection, account_id: str) -> ResearchResult | None:
    facts = _facts_for(con, account_id)
    if facts is None:
        return None
    d = template_draft(facts)
    points = [f"Priority {facts.priority_score:.1f}, {facts.account_tier}", facts.scoring_reason]
    if facts.mom_growth_pct:
        points.append(f"Usage {facts.mom_growth_pct:+.0f}% month over month")
    if facts.ml_job_postings:
        points.append(f"{int(facts.ml_job_postings)} open ML role(s) (Clay)")
    if facts.open_quotes:
        q = facts.open_quotes[0]
        points.append(f"Latest quote {q['quote_id']}: {q['status']}")
    brief = f"{facts.company_summary or facts.account_name + ' is a ' + (facts.industry or 'technology') + ' company.'} {d.narrative}"
    return ResearchResult(Research(brief=brief, outbound_draft=d.outbound_draft, talking_points=points[:5]), "template", 0)


def _claude_research(con: duckdb.DuckDBPyConnection, account_id: str, client: Any | None = None) -> ResearchResult:
    import anthropic

    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60.0)
    messages: list[dict[str, Any]] = [{"role": "user", "content": f"Research account {account_id}. Start with get_account."}]
    started = time.monotonic()
    calls = 0
    response = None
    for _ in range(MAX_TOOL_CALLS + 1):
        response = client.messages.create(model=settings.anthropic_model, max_tokens=2000, system=SYSTEM,
                                          tools=TOOL_SCHEMAS, messages=messages)
        if response.stop_reason == "refusal":
            raise RuntimeError("model refused")
        if response.stop_reason != "tool_use":
            break
        if calls >= MAX_TOOL_CALLS or time.monotonic() - started > TIME_BUDGET_SECONDS:
            raise RuntimeError("tool budget exhausted")
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                calls += 1
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": run_tool(con, block.name, dict(block.input))})
        messages.append({"role": "user", "content": results})
    text = next((b.text for b in (response.content if response else []) if b.type == "text"), "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model response")
    return ResearchResult(Research.model_validate_json(text[start:end + 1]), "claude", calls)


def research_account(con: duckdb.DuckDBPyConnection, account_id: str, correlation_id: str, client: Any | None = None) -> ResearchResult | None:
    result: ResearchResult | None = None
    if settings.ai_enabled and settings.anthropic_api_key or client is not None:
        try:
            result = _claude_research(con, account_id, client=client)
        except (PydanticValidationError, ValueError, RuntimeError) as e:
            log.warning("AI research invalid, using template", extra={"record_id": account_id, "extra": str(e)})
        except Exception as e:  # noqa: BLE001
            log.warning("AI research failed, using template", extra={"record_id": account_id, "extra": str(e)})
    if result is None:
        result = template_research(con, account_id)
    if result is None:
        return None
    con.execute("DELETE FROM account_research WHERE account_id = ?", [account_id])
    con.execute("INSERT INTO account_research VALUES (?,?,?,?,?,?,?,?,?)",
                [f"RS-{uuid.uuid4().hex[:8].upper()}", account_id, result.research.brief, result.research.outbound_draft,
                 json.dumps(result.research.talking_points), result.source, result.tool_calls, datetime.now(), correlation_id])
    write_integration_log(con, "research_agent", STATUS_SUCCESS, correlation_id, "account", account_id)
    return result
