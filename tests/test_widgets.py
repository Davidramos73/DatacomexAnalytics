import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.widgets import (
    Param,
    Widget,
    build_rest_router,
    build_tool_set,
    chart_type_param,
    widget_descriptors,
)


def _noop(con):
    return {}


def test_widget_defaults():
    w = Widget(key="evolution", fn=_noop, params=[], rest_path="/evolution",
               tool_name="market_overview", tool_description="d")
    assert w.span == "full"
    assert w.in_grid is True
    assert w.chart_types is None


def test_chart_type_param_is_enum_with_first_as_default():
    p = chart_type_param(["line", "bar"])
    assert p.name == "chart_type"
    assert p.type == "enum"
    assert p.enum == ["line", "bar"]
    assert p.required is False
    assert p.default == "line"


def test_widget_descriptors_shape():
    w = Widget(
        key="evolution", fn=_noop, rest_path="/api/v1/reports/footwear/evolution",
        tool_name="market_overview", tool_description="d", span="full",
        params=[
            Param("flow", "enum", required=True, default="IMPORT",
                  enum=["IMPORT", "EXPORT"], ui_label="Flujo",
                  ui_options=[{"value": "IMPORT", "label": "Importaciones"}]),
            Param("months", "int", default=24, ui_label="Meses"),
            chart_type_param(["line", "bar"]),
        ],
    )
    d = widget_descriptors([w])["evolution"]
    assert d["rest_path"] == "/api/v1/reports/footwear/evolution"
    assert d["span"] == "full"
    names = [p["name"] for p in d["params"]]
    assert names == ["flow", "months"]          # chart_type dropped
    assert d["params"][0]["ui_options"][0]["label"] == "Importaciones"


def test_build_rest_router_calls_fn_with_params():
    seen = {}

    def evo(con, *, flow, months=24):
        seen["flow"] = flow
        seen["months"] = months
        return {"widget": "evolution", "title": "t", "echarts": {}, "kpis": [], "meta": {}}

    w = Widget(key="evolution", fn=evo, rest_path="/evolution",
               tool_name="mo", tool_description="d",
               params=[Param("flow", "enum", required=True, enum=["IMPORT", "EXPORT"]),
                       Param("months", "int", default=24)])
    app = FastAPI()
    app.include_router(build_rest_router([w], prefix="/r", con_factory=lambda: None))
    client = TestClient(app)

    r = client.get("/r/evolution", params={"flow": "IMPORT", "months": 6})
    assert r.status_code == 200
    assert seen == {"flow": "IMPORT", "months": 6}

    assert client.get("/r/evolution", params={"flow": "NOPE"}).status_code == 422


def test_build_tool_set_defs_and_handlers():
    def mix(con, *, flow, chart_type=None):
        return {"widget": "mix", "flow": flow, "chart_type": chart_type}

    w = Widget(key="mix", fn=mix, rest_path="/mix", tool_name="product_mix",
               tool_description="reparto por tipo",
               chart_types=["pie", "bar"],
               params=[Param("flow", "enum", required=True, enum=["IMPORT", "EXPORT"]),
                       chart_type_param(["pie", "bar"])])
    ts = build_tool_set([w], con=None)

    d = ts["defs"][0]
    assert d["name"] == "product_mix"
    assert d["input_schema"]["properties"]["flow"]["enum"] == ["IMPORT", "EXPORT"]
    assert d["input_schema"]["properties"]["chart_type"]["enum"] == ["pie", "bar"]
    assert d["input_schema"]["required"] == ["flow"]

    out = json.loads(ts["handlers"]["product_mix"](flow="IMPORT", chart_type="bar"))
    assert out == {"widget": "mix", "flow": "IMPORT", "chart_type": "bar"}
