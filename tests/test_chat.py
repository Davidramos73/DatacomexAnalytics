import json
import backend.chat as chat_mod
from backend import events
from backend.agents.llm import AgentResult, ToolCall
from backend.domain import Branding, AppConfig


class FakeDomain:
    settings = None
    system_prompt = "sys"
    prose_closeout_instruction = "resume"

    def app_config(self):
        return AppConfig(Branding("X", "x", "b", "🥾"), [], ["lumen"], [])

    def open_connection(self):
        return None

    def widgets(self):
        return []

    def extra_tools(self):
        return {"defs": [], "handlers": {}}

    def report_prefix(self):
        return None

    def filter_options(self, con):
        return {}

    def web_dir(self):
        return "."

    def step_label(self, name, ti):
        return None

    def finalize(self, agent, con):
        return {"widget": "w", "title": "t", "echarts": {"x": 1}, "kpis": [],
                "meta": {"notes": []}, "data": {"columns": ["a"], "rows": [[1]]}}


def test_run_chat_emits_ordered_events(monkeypatch):
    events_seen = []

    def fake_run_agent(**kw):
        return AgentResult(final_text="", messages=[], tool_calls=[], iterations=1,
                           hit_limit=False)

    def fake_stream_text(**kw):
        yield "Las exporta"
        yield "ciones subieron."

    monkeypatch.setattr(chat_mod.llm, "run_agent", fake_run_agent)
    monkeypatch.setattr(chat_mod.llm, "stream_text", fake_stream_text)

    chat_mod.run_chat(FakeDomain(), "¿cómo van las expo?", events_seen.append)

    kinds = [e.type for e in events_seen]
    assert kinds[0] == "thinking"
    assert "delta" in kinds
    assert kinds[-1] == "done"
    chart = next(e for e in events_seen if e.type == "chart")
    assert chart.data == {"columns": ["a"], "rows": [[1]]}
    text = next(e for e in events_seen if e.type == "text")
    assert text.text == "Las exportaciones subieron."


def test_run_chat_no_envelope_still_finishes(monkeypatch):
    d = FakeDomain()
    d.finalize = lambda agent, con: None
    monkeypatch.setattr(chat_mod.llm, "run_agent",
                        lambda **kw: AgentResult("", [], [], 1, False))
    monkeypatch.setattr(chat_mod.llm, "stream_text", lambda **kw: iter(["ok"]))
    seen = []
    chat_mod.run_chat(d, "hi", seen.append)
    assert [e.type for e in seen][-1] == "done"
    assert not any(e.type == "chart" for e in seen)
