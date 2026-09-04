import json

import duckdb
import pytest

from backend.agents import tools_footwear
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


def test_tool_defs_expose_the_footwear_tools_in_anthropic_shape():
    names = {t["name"] for t in tools_footwear.tool_defs()}
    assert "resolve_footwear_product" in names
    assert names & tools_footwear.REPORT_TOOLS == tools_footwear.REPORT_TOOLS
    for t in tools_footwear.tool_defs():
        assert "input_schema" in t and t["input_schema"]["type"] == "object"


def test_resolve_handler_returns_a_heading(con):
    impls = tools_footwear.handlers(con)
    out = json.loads(impls["resolve_footwear_product"](term="zapatillas deportivas"))
    assert out["heading"] == "6404"


def test_market_overview_handler_returns_a_chart_envelope(con):
    impls = tools_footwear.handlers(con)
    out = json.loads(impls["footwear_market_overview"](flow="import", months=12))
    assert out["widget"] == "monthly_evolution"
    assert out["echarts"]["series"][0]["type"] == "line"


def test_top_partners_handler_uppercases_flow(con):
    impls = tools_footwear.handlers(con)
    out = json.loads(impls["footwear_top_partners"](flow="import", top_n=5))
    assert out["echarts"]["yAxis"]["data"] == ["Vietnam", "China"]
