import json

from chatkit.domain import default_step_label, default_finalize, Branding
from chatkit.agents.llm import AgentResult, ToolCall


def test_default_step_label_formats_kv():
    s = default_step_label("footwear_top_partners", {"flow": "IMPORT", "top_n": 5})
    assert s.label == "footwear_top_partners"
    assert "flow=IMPORT" in s.detail and "top_n=5" in s.detail


def test_default_finalize_returns_last_report_envelope():
    env = {"widget": "countries", "title": "t", "echarts": {}, "kpis": [], "meta": {}}
    agent = AgentResult(
        final_text="", messages=[], iterations=1, hit_limit=False,
        tool_calls=[
            ToolCall("footwear_top_partners", {}, json.dumps(env), is_error=False),
        ],
    )
    assert default_finalize(agent, con=None, report_tool_names={"footwear_top_partners"}) == env


def test_branding_is_a_dataclass():
    b = Branding(name="X", short_name="x", badge="b", favicon="\U0001f97e")
    assert b.name == "X"
