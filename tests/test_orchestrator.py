import json
import pytest
from backend import events
from backend.agents import orchestrator, llm, data_agent


def _dr(**kw):
    base = dict(ok=True, sql="SELECT 1", columns=["region", "rev"],
               rows=[["NA", 8.4], ["EMEA", 6.1]], row_count=2, truncated=False, notes="n")
    base.update(kw)
    return data_agent.DataResult(**base)


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


def _client_returning(final_json):
    """Fake client: first the tool-use turn calling query_data, then the JSON close-out."""
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="q", name="query_data",
                                  input={"question": "revenue by region"})]),
        _Resp("end_turn", [_Block(type="text", text="Here is the breakdown.")]),
        _Resp("end_turn", [_Block(type="text", text=json.dumps(final_json))]),
    ]

    class C:
        calls = []

        @property
        def messages(self):
            m = type("M", (), {})()

            def create(**kw):
                C.calls.append(kw)
                return script.pop(0)

            m.create = create
            return m
    return C()


def test_rows_to_records():
    recs = orchestrator.rows_to_records(["a", "b"], [[1, 2], [3, 4]])
    assert recs == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_clean_history_sanitizes_turns():
    turns = [
        {"role": "assistant", "content": "leading assistant, dropped"},
        {"role": "user", "content": "Q1"},
        {"role": "user", "content": "Q1 (edited)"},   # consecutive -> keep last
        {"role": "assistant", "content": "A1"},
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": ""},              # empty -> skipped
        {"role": "user", "content": "Q2"},
    ]
    assert orchestrator.clean_history(turns) == [
        {"role": "user", "content": "Q1 (edited)"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]


def test_clean_history_caps_length():
    turns = []
    for i in range(20):
        turns.append({"role": "user", "content": f"q{i}"})
        turns.append({"role": "assistant", "content": f"a{i}"})
    out = orchestrator.clean_history(turns)
    assert len(out) == orchestrator.MAX_HISTORY_TURNS
    assert out[-1] == {"role": "assistant", "content": "a19"}


def test_run_seeds_prior_conversation(monkeypatch):
    final = {
        "answer": "ok", "chart_title": "t", "chart_meta": "m",
        "echarts_option": {"series": [{"type": "bar"}]},
    }
    client = _client_returning(final)
    type(client).calls = []
    monkeypatch.setattr(llm, "get_client", lambda: client)
    history = [
        {"role": "user", "content": "revenue by region?"},
        {"role": "assistant", "content": "North America leads."},
    ]
    orchestrator.run(
        "now by month", [].append, history=history, data_fn=lambda q, s, **k: _dr()
    )
    # run_agent keeps appending to this list, so assert on the seeded prefix.
    first_messages = type(client).calls[0]["messages"]
    assert first_messages[0] == {"role": "user", "content": "revenue by region?"}
    assert first_messages[1] == {"role": "assistant", "content": "North America leads."}
    assert first_messages[2] == {"role": "user", "content": "now by month"}


def test_validate_binds_dataset_source():
    option = {"series": [{"type": "bar"}], "xAxis": {"type": "category"}, "yAxis": {}}
    out = orchestrator.validate_echarts_option(option, [{"region": "NA", "rev": 8.4}])
    assert out["dataset"]["source"] == [{"region": "NA", "rev": 8.4}]


def test_validate_keeps_inline_dataset():
    option = {"series": [{"type": "pie"}],
              "dataset": {"source": [{"k": "a", "v": 1}]}}
    out = orchestrator.validate_echarts_option(option, [{"k": "b", "v": 2}])
    assert out["dataset"]["source"] == [{"k": "a", "v": 1}]


def test_validate_rejects_seriesless_option():
    with pytest.raises(orchestrator.SpecError):
        orchestrator.validate_echarts_option({"xAxis": {}}, [])


def test_run_emits_chart(monkeypatch):
    final = {
        "answer": "North America leads.",
        "chart_title": "Q3 revenue by region",
        "chart_meta": "bar · fct_orders · 2 rows",
        "echarts_option": {
            "xAxis": {"type": "category"},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "encode": {"x": "region", "y": "rev"}}],
        },
    }
    client = _client_returning(final)
    type(client).calls = []
    monkeypatch.setattr(llm, "get_client", lambda: client)
    seen = []
    orchestrator.run("revenue by region?", seen.append, data_fn=lambda q, s, **k: _dr())

    kinds = [e.type for e in seen]
    assert "text" in kinds and "chart" in kinds and "done" in kinds
    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert chart.spec["dataset"]["source"][0]["region"] == "NA"
    assert chart.title == "Q3 revenue by region"
    # close-out call must carry tools= (history contains tool_use blocks)
    assert "tools" in type(client).calls[-1]


def test_run_emits_error_on_bad_spec(monkeypatch):
    final = {"answer": "x", "chart_title": "t", "chart_meta": "m",
             "echarts_option": {"xAxis": {}}}
    client = _client_returning(final)
    monkeypatch.setattr(llm, "get_client", lambda: client)
    seen = []
    orchestrator.run("q", seen.append, data_fn=lambda q, s, **k: _dr())
    assert any(isinstance(e, events.ErrorEvent) for e in seen)
    assert any(isinstance(e, events.Done) for e in seen)


def test_run_emits_error_when_data_agent_fails(monkeypatch):
    client = _client_returning({})
    monkeypatch.setattr(llm, "get_client", lambda: client)
    seen = []
    orchestrator.run("q", seen.append, data_fn=lambda q, s, **k: _dr(ok=False, error="no query"))
    assert any(isinstance(e, events.ErrorEvent) for e in seen)
    assert any(isinstance(e, events.Done) for e in seen)
