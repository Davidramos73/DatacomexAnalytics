import dataclasses
from backend import events
from backend.agents import llm


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class FakeMessages:
    """Scripted Claude: returns queued responses in order."""
    def __init__(self, script): self._script = list(script); self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._script.pop(0)


class FakeClient:
    def __init__(self, script): self.messages = FakeMessages(script)


def test_runs_tool_then_finishes(monkeypatch):
    script = [
        _Resp("tool_use", [
            _Block(type="tool_use", id="t1", name="run_sql", input={"sql": "SELECT 1"}),
        ]),
        _Resp("end_turn", [_Block(type="text", text="done: 1 row")]),
    ]
    fake = FakeClient(script)
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    seen = []
    result = llm.run_agent(
        model="m", system="s",
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "run_sql"}],
        tool_impls={"run_sql": lambda sql: f"ran {sql}"},
        sink=seen.append,
    )
    assert result.final_text == "done: 1 row"
    assert result.iterations == 2
    assert result.hit_limit is False
    assert [tc.name for tc in result.tool_calls] == ["run_sql"]
    assert result.tool_calls[0].result == "ran SELECT 1"
    assert any(isinstance(e, events.Step) for e in seen)


def test_tool_exception_becomes_error_result(monkeypatch):
    script = [
        _Resp("tool_use", [
            _Block(type="tool_use", id="t1", name="boom", input={}),
        ]),
        _Resp("end_turn", [_Block(type="text", text="recovered")]),
    ]
    fake = FakeClient(script)
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    def boom(): raise ValueError("nope")

    result = llm.run_agent(
        model="m", system="s", messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "boom"}], tool_impls={"boom": boom}, sink=lambda e: None,
    )
    assert result.tool_calls[0].is_error is True
    assert "nope" in result.tool_calls[0].result


def test_hits_iteration_limit(monkeypatch):
    loop_resp = _Resp("tool_use", [
        _Block(type="tool_use", id="t", name="noop", input={}),
    ])

    class Loop:
        messages = type("M", (), {"create": staticmethod(lambda **k: loop_resp)})()

    monkeypatch.setattr(llm, "get_client", lambda: Loop())
    seen = []
    result = llm.run_agent(
        model="m", system="s", messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "noop"}], tool_impls={"noop": lambda: "ok"},
        sink=seen.append, max_iters=3,
    )
    assert result.hit_limit is True
    assert result.iterations == 3
    assert any(isinstance(e, events.ErrorEvent) for e in seen)
