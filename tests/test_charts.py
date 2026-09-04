import pytest

from backend import charts

COLS = ["region", "revenue", "margin"]
ROWS = [["NA", 8.4, 61.0], ["EMEA", 6.1, 55.0], ["APAC", 2.7, 48.0]]


def test_bar_binds_dataset_and_encode():
    opt = charts.build_option(
        {"chart_type": "bar", "x": "region", "y": ["revenue"], "series_by": None},
        COLS, ROWS,
    )
    assert opt["dataset"]["source"][0] == {"region": "NA", "revenue": 8.4, "margin": 61.0}
    assert opt["xAxis"]["type"] == "category"
    assert opt["series"] == [
        {"type": "bar", "name": "revenue", "encode": {"x": "region", "y": "revenue"}}
    ]


def test_multiple_y_columns_add_legend():
    opt = charts.build_option(
        {"chart_type": "line", "x": "region", "y": ["revenue", "margin"], "series_by": None},
        COLS, ROWS,
    )
    assert [s["name"] for s in opt["series"]] == ["revenue", "margin"]
    assert "legend" in opt


def test_pie_uses_item_name_and_value():
    opt = charts.build_option(
        {"chart_type": "pie", "x": "region", "y": ["revenue"], "series_by": None},
        COLS, ROWS,
    )
    assert opt["series"][0]["type"] == "pie"
    assert opt["series"][0]["encode"] == {"itemName": "region", "value": "revenue"}
    assert "xAxis" not in opt


def test_scatter_two_value_axes():
    opt = charts.build_option(
        {"chart_type": "scatter", "x": "revenue", "y": ["margin"], "series_by": None},
        COLS, ROWS,
    )
    assert opt["xAxis"]["type"] == "value"
    assert opt["yAxis"]["type"] == "value"
    assert opt["series"][0]["encode"] == {"x": "revenue", "y": "margin"}


def test_series_by_pivots_into_one_series_per_group():
    cols = ["month", "channel", "revenue"]
    rows = [
        ["Jan", "Direct", 10], ["Jan", "Partner", 4],
        ["Feb", "Direct", 12], ["Feb", "Partner", 5],
    ]
    opt = charts.build_option(
        {"chart_type": "bar", "x": "month", "y": ["revenue"], "series_by": "channel"},
        cols, rows,
    )
    assert opt["xAxis"]["data"] == ["Jan", "Feb"]
    names = {s["name"]: s["data"] for s in opt["series"]}
    assert names == {"Direct": [10, 12], "Partner": [4, 5]}
    assert "legend" in opt


def test_string_y_is_accepted():
    opt = charts.build_option(
        {"chart_type": "bar", "x": "region", "y": "revenue", "series_by": None},
        COLS, ROWS,
    )
    assert opt["series"][0]["name"] == "revenue"


@pytest.mark.parametrize("bad", [
    {"chart_type": "radar", "x": "region", "y": ["revenue"], "series_by": None},
    {"chart_type": "bar", "x": "nope", "y": ["revenue"], "series_by": None},
    {"chart_type": "bar", "x": "region", "y": [], "series_by": None},
    {"chart_type": "bar", "x": "region", "y": ["revenue"], "series_by": "nope"},
    "not a dict",
])
def test_invalid_mappings_raise(bad):
    with pytest.raises(charts.ChartError):
        charts.build_option(bad, COLS, ROWS)


def test_rows_are_capped():
    rows = [["r%d" % i, i] for i in range(500)]
    opt = charts.build_option(
        {"chart_type": "bar", "x": "k", "y": ["v"], "series_by": None},
        ["k", "v"], rows,
    )
    assert len(opt["dataset"]["source"]) == charts.MAX_POINTS
