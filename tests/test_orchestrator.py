import json
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


class _FakeStream:
    """Stand-in for anthropic client.messages.stream(...) context manager."""
    def __init__(self, text): self._text = text
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def text_stream(self):
        yield self._text


PROSE = "North America leads the quarter."


def _client_returning(chart_mapping):
    """Fake Anthropic client: the query_data tool turn, then (prose is streamed)
    the structured chart-mapping close-out."""
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="q", name="query_data",
                                  input={"question": "revenue by region"})]),
        _Resp("end_turn", [_Block(type="text", text="Here is the breakdown.")]),
        _Resp("end_turn", [_Block(type="text", text=json.dumps(chart_mapping))]),
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
            m.stream = lambda **kw: _FakeStream(PROSE)
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
        "chart_type": "bar", "chart_x": "region", "chart_y": ["rev"], "chart_series_by": None,
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


def test_chartability_prefers_a_real_breakdown_over_a_diagnostic():
    breakdown = _dr(columns=["region", "rev"],
                    rows=[["NA", 8.4], ["EMEA", 6.1], ["APAC", 2.7]], row_count=3)
    diagnostic = _dr(columns=["min_rev", "max_rev"], rows=[[1.0, 9.0]], row_count=1)
    assert orchestrator._chartability(breakdown) > orchestrator._chartability(diagnostic)


def test_run_charts_the_best_dataset_not_the_last(monkeypatch):
    good = _dr(columns=["region", "rev"],
               rows=[["NA", 8.4], ["EMEA", 6.1], ["APAC", 2.7]], row_count=3)
    diagnostic = _dr(columns=["min_rev", "max_rev"], rows=[[1.0, 9.0]], row_count=1)
    results = iter([good, diagnostic])

    final = {"chart_title": "t", "chart_meta": "m",
             "chart_type": "bar", "chart_x": "region", "chart_y": ["rev"],
             "chart_series_by": None}
    # two query_data tool calls, then the structured chart-mapping close-out
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="q1", name="query_data",
                                  input={"question": "breakdown"})]),
        _Resp("tool_use", [_Block(type="tool_use", id="q2", name="query_data",
                                  input={"question": "diagnostic min/max"})]),
        _Resp("end_turn", [_Block(type="text", text="here")]),
        _Resp("end_turn", [_Block(type="text", text=json.dumps(final))]),
    ]

    class C:
        @property
        def messages(self):
            m = type("M", (), {})()
            m.create = lambda **kw: script.pop(0)
            m.stream = lambda **kw: _FakeStream("prose")
            return m

    monkeypatch.setattr(llm, "get_client", lambda: C())
    seen = []
    orchestrator.run("q", seen.append, data_fn=lambda q, s, **k: next(results))

    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert [row["region"] for row in chart.spec["dataset"]["source"]] == ["NA", "EMEA", "APAC"]


def test_run_emits_chart(monkeypatch):
    final = {
        "chart_title": "Q3 revenue by region",
        "chart_meta": "bar · fct_orders · 2 rows",
        "chart_type": "bar", "chart_x": "region", "chart_y": ["rev"], "chart_series_by": None,
    }
    client = _client_returning(final)
    type(client).calls = []
    monkeypatch.setattr(llm, "get_client", lambda: client)
    seen = []
    orchestrator.run("revenue by region?", seen.append, data_fn=lambda q, s, **k: _dr())

    kinds = [e.type for e in seen]
    assert "delta" in kinds and "text" in kinds and "chart" in kinds and "done" in kinds
    # the streamed prose is consolidated into the final text event
    assert next(e for e in seen if isinstance(e, events.Text)).text == PROSE
    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert chart.spec["dataset"]["source"][0]["region"] == "NA"
    assert chart.spec["series"][0]["type"] == "bar"
    assert chart.title == "Q3 revenue by region"
    # the mapping close-out call carries tools= (history has tool_use blocks)
    assert "tools" in type(client).calls[-1]


def test_run_emits_error_on_bad_chart(monkeypatch):
    # an unknown column is recoverable now; an unsupported chart_type is not
    final = {"answer": "x", "chart_title": "t", "chart_meta": "m",
             "chart_type": "donut", "chart_x": "region", "chart_y": ["rev"],
             "chart_series_by": None}
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
