from projects.footwear.services.widgets import WIDGETS, REST_PREFIX
from chatkit.widgets import build_tool_set


def test_widget_keys_and_tool_names():
    keys = {w.key for w in WIDGETS}
    assert keys == {"evolution", "countries", "mix", "price", "balance"}
    names = {w.tool_name for w in WIDGETS}
    assert "footwear_market_overview" in names


def test_every_widget_param_named_heading_not_taric():
    for w in WIDGETS:
        assert all(p.name != "taric" for p in w.params)


def test_tool_set_builds():
    ts = build_tool_set(WIDGETS, con=None)
    assert len(ts["defs"]) == 5


def test_months_param_carries_ui_bounds():
    months = next(
        p for w in WIDGETS for p in w.params if p.name == "months"
    )
    assert months.ui_min == 6
    assert months.ui_max == 36
