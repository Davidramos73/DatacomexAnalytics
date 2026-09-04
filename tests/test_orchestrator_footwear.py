import json

import duckdb
import pytest

from backend import events
from backend.agents import llm, orchestrator_footwear
from backend.warehouse.datacomex_schema import HEADINGS, SCHEMA_DDL


@pytest.fixture
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "dc.duckdb"))
    c.execute(SCHEMA_DDL)
    c.executemany(
        "INSERT INTO datacomex.taric_tree VALUES (?, ?, ?, ?)",
        [("64", None, 2, "Calzado")]
        + [(h, "64", 4, d) for h, (d, _) in HEADINGS.items()],
    )
    c.executemany(
        "INSERT INTO datacomex.trade_flows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("IMPORT", "2024-01", 2024, 1, "CHN", "China", "640411", "64", "6404",
             40_000_000, 3_000_000, None, False),
            ("IMPORT", "2024-01", 2024, 1, "VNM", "Vietnam", "640411", "64", "6404",
             10_000_000, 1_000_000, None, False),
        ],
    )
    yield c
    c.close()


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


class _FakeStream:
    def __init__(self, text): self._text = text
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def text_stream(self):
        yield self._text


def _client(script, prose="China lidera las importaciones."):
    class C:
        @property
        def messages(self):
            m = type("M", (), {})()
            m.create = lambda **kw: script.pop(0)
            m.stream = lambda **kw: _FakeStream(prose)
            return m
    return C()


def test_report_tool_result_is_charted_directly(monkeypatch, con):
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="t1",
                                  name="footwear_top_partners",
                                  input={"flow": "IMPORT", "top_n": 5})]),
        _Resp("end_turn", [_Block(type="text", text="Listo.")]),
    ]
    monkeypatch.setattr(llm, "get_client", lambda: _client(script))
    seen = []
    orchestrator_footwear.run("¿de dónde importamos calzado?", seen.append,
                              con_factory=lambda: con)

    kinds = [e.type for e in seen]
    assert "delta" in kinds and "text" in kinds and "chart" in kinds and "done" in kinds
    chart = next(e for e in seen if isinstance(e, events.Chart))
    # the pre-built ECharts option from the service is used verbatim
    assert chart.spec["series"][0]["type"] == "bar"
    assert chart.spec["yAxis"]["data"] == ["Vietnam", "China"]
    assert "líder" in chart.meta.lower() or "lider" in chart.meta.lower()
    assert next(e for e in seen if isinstance(e, events.Text)).text == \
        "China lidera las importaciones."


def test_resolve_then_report(monkeypatch, con):
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="r", name="resolve_footwear_product",
                                  input={"term": "deportivas"})]),
        _Resp("tool_use", [_Block(type="tool_use", id="t", name="footwear_market_overview",
                                  input={"flow": "IMPORT", "heading": "6404"})]),
        _Resp("end_turn", [_Block(type="text", text="ok")]),
    ]
    monkeypatch.setattr(llm, "get_client", lambda: _client(script))
    seen = []
    orchestrator_footwear.run("evolución de las deportivas", seen.append,
                              con_factory=lambda: con)
    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert chart.spec["series"][0]["type"] == "line"


def test_answer_without_a_report_emits_text_only(monkeypatch, con):
    script = [
        _Resp("end_turn", [_Block(type="text",
                                  text="Puedo darte evolución, socios, mix o precio.")]),
    ]
    monkeypatch.setattr(llm, "get_client", lambda: _client(script))
    seen = []
    orchestrator_footwear.run("hola", seen.append, con_factory=lambda: con)
    kinds = [e.type for e in seen]
    assert "chart" not in kinds
    assert "text" in kinds and "done" in kinds
    assert next(e for e in seen if isinstance(e, events.Text)).text.startswith("Puedo")
