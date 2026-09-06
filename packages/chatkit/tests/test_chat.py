import chatkit.chat as chat_mod
from chatkit import events
from chatkit.agents.llm import AgentResult
from chatkit.domain import Branding, AppConfig


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

    # Full relative order: last delta -> chart.render step -> text -> chart -> done
    last_delta = max(i for i, e in enumerate(events_seen) if e.type == "delta")
    render_step = next(i for i, e in enumerate(events_seen)
                       if getattr(e, "label", None) == "chart.render")
    text_i = next(i for i, e in enumerate(events_seen) if e.type == "text")
    chart_i = next(i for i, e in enumerate(events_seen) if e.type == "chart")
    done_i = next(i for i, e in enumerate(events_seen) if e.type == "done")
    assert last_delta < render_step < text_i < chart_i < done_i


def test_run_chat_hit_limit_appends_note_and_meta_join(monkeypatch):
    d = FakeDomain()
    d.finalize = lambda agent, con: {
        "title": "t", "echarts": {"x": 1},
        "kpis": [{"label": "Var", "value": "+5%", "tone": "positive"}],
        "meta": {"notes": ["nota previa"]},
        "data": {"columns": ["a"], "rows": [[1]]},
    }
    monkeypatch.setattr(chat_mod.llm, "run_agent",
                        lambda **kw: AgentResult("", [], [], 1, True))
    monkeypatch.setattr(chat_mod.llm, "stream_text", lambda **kw: iter(["ok"]))
    seen = []
    chat_mod.run_chat(d, "hi", seen.append)

    chart = next(e for e in seen if e.type == "chart")
    assert "Var: +5%" in chart.meta
    assert "nota previa" in chart.meta
    assert "respuesta truncada: se alcanzó el límite de pasos" in chart.meta


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
    assert not any(e.type == "error" for e in seen)
