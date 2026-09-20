"""v2 item 6: bounded research agent, tested with a fake model client (no API key)."""
import json
from types import SimpleNamespace

import duckdb

from src.ai.research_agent import MAX_TOOL_CALLS, research_account
from src.ai.tools import TOOL_SCHEMAS, run_tool


class FakeClient:
    """Emits one tool call per turn for `n_tool_turns` turns, then a final JSON answer."""

    def __init__(self, n_tool_turns=2, final=None, bad_final=False):
        self.n = n_tool_turns
        self.turn = 0
        self.final = final or {"brief": "Initech ML is growing fast.", "outbound_draft": "Hi team, ...",
                               "talking_points": ["usage +40%", "2 ML roles"]}
        self.bad_final = bad_final
        self.messages = SimpleNamespace(create=self.create)
        self.seen_tools = []

    def create(self, **kw):
        self.turn += 1
        if self.turn <= self.n:
            name = TOOL_SCHEMAS[(self.turn - 1) % len(TOOL_SCHEMAS)]["name"]
            args = {"account_id": "ACC-00003", **({"days": 90} if name == "get_signals" else {})}
            self.seen_tools.append(name)
            return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", id=f"t{self.turn}", name=name, input=args)])
        text = "not json at all" if self.bad_final else json.dumps(self.final)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def test_tools_are_read_only_and_answer(pipeline_db):
    con = duckdb.connect(str(pipeline_db), read_only=True)
    acct = json.loads(run_tool(con, "get_account", {"account_id": "ACC-00003"}))
    assert acct["account_tier"] == "Tier 1" and acct["priority_score"] == 87.0
    sig = json.loads(run_tool(con, "get_signals", {"account_id": "ACC-00003", "days": 90}))
    assert any(s["type"] == "pricing_page_visit" for s in sig["signals"])
    assert "error" in json.loads(run_tool(con, "nope", {}))
    con.close()


def test_template_path_without_key(pipeline_db):
    con = duckdb.connect(str(pipeline_db))
    res = research_account(con, "ACC-00003", "run-t")
    assert res.source == "template" and res.tool_calls == 0 and "Initech ML" in res.research.brief
    row = con.execute("SELECT source, tool_calls FROM account_research WHERE account_id = 'ACC-00003'").fetchone()
    assert row == ("template", 0)
    con.close()


def test_agent_loop_with_fake_model(pipeline_db):
    con = duckdb.connect(str(pipeline_db))
    fake = FakeClient(n_tool_turns=3)
    res = research_account(con, "ACC-00003", "run-t", client=fake)
    assert res.source == "claude" and res.tool_calls == 3 and fake.seen_tools[0] == "get_account"
    assert res.research.talking_points == ["usage +40%", "2 ML roles"]
    con.close()


def test_agent_falls_back_when_budget_exhausted(pipeline_db):
    con = duckdb.connect(str(pipeline_db))
    res = research_account(con, "ACC-00003", "run-t", client=FakeClient(n_tool_turns=MAX_TOOL_CALLS + 3))
    assert res.source == "template"
    con.close()


def test_agent_falls_back_on_invalid_output(pipeline_db):
    con = duckdb.connect(str(pipeline_db))
    res = research_account(con, "ACC-00003", "run-t", client=FakeClient(n_tool_turns=1, bad_final=True))
    assert res.source == "template"
    con.close()
