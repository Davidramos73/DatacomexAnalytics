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


def test_bad_chart_type_raises():
    with pytest.raises(charts.ChartError):
        charts.build_option(
            {"chart_type": "radar", "x": "region", "y": ["revenue"], "series_by": None},
            COLS, ROWS,
        )


def test_non_dict_mapping_raises():
    with pytest.raises(charts.ChartError):
        charts.build_option("not a dict", COLS, ROWS)


def test_empty_result_raises():
    with pytest.raises(charts.ChartError):
        charts.build_option(
            {"chart_type": "bar", "x": "region", "y": ["revenue"], "series_by": None},
            [], [],
        )


def test_unknown_x_falls_back_to_a_category_column():
    opt = charts.build_option(
        {"chart_type": "bar", "x": "segment", "y": ["revenue"], "series_by": None},
        COLS, ROWS,  # no "segment" column here
    )
    assert opt["series"][0]["encode"]["x"] == "region"  # first non-numeric column


def test_unknown_y_falls_back_to_numeric_columns():
    opt = charts.build_option(
        {"chart_type": "bar", "x": "region", "y": ["nope"], "series_by": None},
        COLS, ROWS,
    )
    assert [s["name"] for s in opt["series"]] == ["revenue", "margin"]


def test_unknown_series_by_is_dropped():
    opt = charts.build_option(
        {"chart_type": "bar", "x": "region", "y": ["revenue"], "series_by": "nope"},
        COLS, ROWS,
    )
    assert "data" not in opt["series"][0]  # not pivoted
    assert opt["series"][0]["encode"] == {"x": "region", "y": "revenue"}


def test_rows_are_capped():
    rows = [["r%d" % i, i] for i in range(500)]
    opt = charts.build_option(
        {"chart_type": "bar", "x": "k", "y": ["v"], "series_by": None},
        ["k", "v"], rows,
    )
    assert len(opt["dataset"]["source"]) == charts.MAX_POINTS
