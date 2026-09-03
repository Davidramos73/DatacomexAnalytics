import json
import pytest
from backend.agents import data_agent, llm
from backend.warehouse import db, seed


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


class FakeClient:
    def __init__(self, script): self._s = list(script)
    class _M:
        pass
    @property
    def messages(self):
        m = FakeClient._M()
        m.create = lambda **kw: self._s.pop(0)
        return m


@pytest.fixture
def con(tmp_path):
    p = tmp_path / "w.duckdb"
    seed.build(p)
    c = db.connect(p)
    yield c
    c.close()


def test_returns_rows_from_last_successful_query(monkeypatch, con):
    sql = "SELECT region, SUM(net_revenue) AS rev FROM fct_orders GROUP BY 1 ORDER BY 2 DESC"
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="a", name="run_sql", input={"sql": sql})]),
        _Resp("end_turn", [_Block(type="text", text="Revenue is concentrated in North America.")]),
    ]
    monkeypatch.setattr(llm, "get_client", lambda: FakeClient(script))

    seen = []
    result = data_agent.answer_data_question("revenue by region", seen.append, con=con)

    assert result.ok is True
    assert result.columns == ["region", "rev"]
    assert result.row_count > 0
    assert "North America" in result.notes
    assert any(getattr(e, "label", "") == "sql.query" for e in seen)


def test_no_successful_query_returns_not_ok(monkeypatch, con):
    script = [_Resp("end_turn", [_Block(type="text", text="I could not do it.")])]
    monkeypatch.setattr(llm, "get_client", lambda: FakeClient(script))
    result = data_agent.answer_data_question("???", lambda e: None, con=con)
    assert result.ok is False
    assert result.error
