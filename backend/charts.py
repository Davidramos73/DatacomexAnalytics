"""Deterministic ECharts option builder.

The model only picks a mapping (chart type + which result columns are x / y /
series); this module turns that plus the rows into a valid ECharts `option`.
Colours, fonts and the page background are left to the registered UI theme.
"""
from __future__ import annotations

MAX_POINTS = 200
ALLOWED_TYPES = ("bar", "line", "pie", "scatter")


class ChartError(ValueError):
    """The model's chart mapping doesn't fit the data."""


def _distinct(values: list) -> list:
    seen: dict = {}
    for v in values:
        seen.setdefault(v, None)
    return list(seen)


def build_option(chart: dict, columns: list[str], rows: list[list]) -> dict:
    if not isinstance(chart, dict):
        raise ChartError("chart mapping is not an object")

    ctype = chart.get("chart_type") or "bar"  # default when the model omits it
    if ctype not in ALLOWED_TYPES:
        raise ChartError(f"unsupported chart_type {ctype!r}")

    x = chart.get("x")
    y = chart.get("y")
    ys = [y] if isinstance(y, str) else [c for c in (y or []) if c]
    series_by = chart.get("series_by")
    if isinstance(series_by, str) and series_by.strip().lower() in ("", "null", "none"):
        series_by = None

    known = list(columns)
    for col in [x, *ys, *([series_by] if series_by else [])]:
        if col not in known:
            raise ChartError(f"column {col!r} is not in the result {known}")
    if not ys:
        raise ChartError("no y column given")

    records = [dict(zip(columns, r)) for r in rows][:MAX_POINTS]
    option: dict = {
        "dataset": {"source": records},
        "tooltip": {"trigger": "item" if ctype == "pie" else "axis"},
    }

    if ctype == "pie":
        option["tooltip"]["trigger"] = "item"
        option["series"] = [
            {
                "type": "pie",
                "radius": ["38%", "70%"],
                "encode": {"itemName": x, "value": ys[0]},
                "label": {"formatter": "{b}: {d}%"},
            }
        ]
        return option

    if ctype == "scatter":
        option["xAxis"] = {"type": "value", "name": x}
        option["yAxis"] = {"type": "value", "name": ys[0]}
        option["series"] = [{"type": "scatter", "encode": {"x": x, "y": ys[0]}}]
        return option

    # bar / line
    option["xAxis"] = {"type": "category"}
    option["yAxis"] = {"type": "value"}

    if series_by:
        cats = _distinct([rec[x] for rec in records])
        groups = _distinct([rec[series_by] for rec in records])
        col = ys[0]
        lookup = {(rec[x], rec[series_by]): rec[col] for rec in records}
        option["xAxis"]["data"] = cats
        option["legend"] = {}
        option["series"] = [
            {"type": ctype, "name": g, "data": [lookup.get((c, g)) for c in cats]}
            for g in groups
        ]
    else:
        option["series"] = [
            {"type": ctype, "name": col, "encode": {"x": x, "y": col}} for col in ys
        ]
        if len(ys) > 1:
            option["legend"] = {}

    return option
