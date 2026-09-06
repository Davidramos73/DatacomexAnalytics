from backend.sql_domain import SqlDomain


def test_widgets_empty_and_query_tool_present():
    d = SqlDomain()
    assert d.widgets() == []
    assert d.extra_tools()["defs"][0]["name"] == "query_data"


def test_finalize_builds_envelope_from_dataset(monkeypatch):
    d = SqlDomain()
    from backend.agents.data_agent import DataResult
    d._datasets = [DataResult(ok=True, sql="SELECT 1", columns=["region", "rev"],
                              rows=[["EMEA", 10], ["APAC", 7]], row_count=2)]
    monkeypatch.setattr(d, "_chart_mapping", lambda agent: {
        "chart_title": "Rev by region", "chart_meta": "",
        "chart_type": "bar", "chart_x": "region", "chart_y": ["rev"],
        "chart_series_by": None})
    env = d.finalize(agent=None, con=None)
    assert env["title"] == "Rev by region"
    assert env["data"]["columns"] == ["region", "rev"]
    assert env["echarts"]["series"]
