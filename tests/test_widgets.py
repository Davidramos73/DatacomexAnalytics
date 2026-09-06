from backend.widgets import Param, Widget, chart_type_param, widget_descriptors


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
