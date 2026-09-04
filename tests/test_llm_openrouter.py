import json

import pytest

from backend.agents import llm


# --- fakes mimicking the OpenAI SDK response shape -------------------------- #
class _Func:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = _Func(name, arguments)


class _Message:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Resp:
    def __init__(self, message):
        self.choices = [type("C", (), {"message": message})()]


class FakeOpenAI:
    def __init__(self, script):
        self._script = list(script)
        self.calls = []
        outer = self

        class _Completions:
            def create(self, **kw):
                outer.calls.append(kw)
                return outer._script.pop(0)

        self.chat = type("Chat", (), {"completions": _Completions()})()


@pytest.fixture
def as_openrouter(monkeypatch):
    monkeypatch.setattr(llm.config, "LLM_PROVIDER", "openrouter")
    llm.reset_client()
    yield
    llm.reset_client()


def test_to_openai_tools_shape():
    out = llm.to_openai_tools(
        [{"name": "f", "description": "d", "input_schema": {"type": "object"}}]
    )
    assert out == [
        {
            "type": "function",
            "function": {
                "name": "f",
                "description": "d",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_openai_agent_runs_tool_then_finishes(monkeypatch, as_openrouter):
    script = [
        _Resp(_Message(tool_calls=[_ToolCall("c1", "run_sql", '{"sql": "SELECT 1"}')])),
        _Resp(_Message(content="done: 1 row")),
    ]
    fake = FakeOpenAI(script)
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    seen = []
    result = llm.run_agent(
        model="m",
        system="sys",
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "run_sql", "description": "x", "input_schema": {"type": "object"}}],
        tool_impls={"run_sql": lambda sql: f"ran {sql}"},
        sink=seen.append,
    )

    assert result.final_text == "done: 1 row"
    assert [tc.name for tc in result.tool_calls] == ["run_sql"]
    assert result.tool_calls[0].result == "ran SELECT 1"

    first = fake.calls[0]
    assert first["messages"][0] == {"role": "system", "content": "sys"}
    assert first["tools"][0]["type"] == "function"
    assert first["tools"][0]["function"]["name"] == "run_sql"
    # second call carries the tool result
    assert any(m["role"] == "tool" for m in fake.calls[1]["messages"])


def test_openai_agent_hits_iteration_limit(monkeypatch, as_openrouter):
    loop = _Resp(_Message(tool_calls=[_ToolCall("t", "noop", "{}")]))

    class Loop(FakeOpenAI):
        def __init__(self):
            super().__init__([])

        def _pop(self):
            return loop

    fake = FakeOpenAI([loop, loop, loop, loop])
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    seen = []
    result = llm.run_agent(
        model="m",
        system="s",
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "noop"}],
        tool_impls={"noop": lambda: "ok"},
        sink=seen.append,
        max_iters=3,
    )
    assert result.hit_limit is True
    assert result.iterations == 3


def test_structured_json_openai(monkeypatch, as_openrouter):
    fake = FakeOpenAI(
        [
            _Resp(
                _Message(
                    content=json.dumps(
                        {
                            "answer": "a",
                            "chart_title": "t",
                            "chart_meta": "m",
                            "echarts_option": "{}",
                        }
                    )
                )
            )
        ]
    )
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    out = llm.structured_json(
        model="m",
        system="sys",
        messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
        ],
        tools=[{"name": "f"}],
        schema={
            "type": "object",
            "properties": {
                "answer": {}, "chart_title": {}, "chart_meta": {}, "echarts_option": {}
            },
        },
        schema_name="chart_response",
    )
    assert out["chart_title"] == "t"
    assert fake.calls[0]["response_format"]["type"] == "json_schema"
    assert fake.calls[0]["response_format"]["json_schema"]["strict"] is True
    # the schema's keys are surfaced to the model as an instruction
    assert "echarts_option" in fake.calls[0]["messages"][-1]["content"]
    assert "tools" not in fake.calls[0]


def test_structured_json_openai_retries_on_bad_json(monkeypatch, as_openrouter):
    fake = FakeOpenAI([
        _Resp(_Message(content="not json at all")),
        _Resp(_Message(content='{"ok": true}')),
    ])
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    out = llm.structured_json(
        model="m", system="s",
        messages=[{"role": "user", "content": "q"}],
        tools=[], schema={"type": "object", "properties": {}},
    )
    assert out == {"ok": True}
    assert len(fake.calls) == 2
    # first attempt strict json_schema, retry falls back to json_object
    assert fake.calls[0]["response_format"]["type"] == "json_schema"
    assert fake.calls[1]["response_format"] == {"type": "json_object"}
