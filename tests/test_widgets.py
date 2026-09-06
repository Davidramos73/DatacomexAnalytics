from backend.widgets import Param, Widget, chart_type_param


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
