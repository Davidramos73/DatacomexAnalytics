"""Footwear (DataComex TARIC chapter 64) query + chartSpec layer.

The single place with domain SQL. REST report endpoints and the agent tools
are thin wrappers over these functions, so the reports page and the chat
never diverge.
"""
from __future__ import annotations

from backend.warehouse.datacomex_schema import SHORT_LABEL

_FLOW_LABEL = {"IMPORT": "Importaciones", "EXPORT": "Exportaciones"}


def _scope(heading: str) -> tuple[str, str]:
    """(sql predicate, param) for a chapter ('64') or a heading ('64xx')."""
    heading = (heading or "64").strip()
    if len(heading) <= 2:
        return "chapter = ?", "64"
    return "heading = ?", heading


def _pct(value: float, base: float) -> float | None:
    if not base:
        return None
    return (value / base - 1.0) * 100.0


def _pct_kpi(label: str, value: float, base: float) -> dict:
    change = _pct(value, base)
    if change is None:
        return {"label": label, "value": "n/d", "tone": "neutral"}
    tone = "positive" if change > 0.05 else "negative" if change < -0.05 else "neutral"
    return {"label": label, "value": f"{change:+.1f}%", "tone": tone}


# colloquial term -> heading. First matching keyword wins.
_HEADING_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("6401", ("agua", "impermeable", "lluvia", "goma", "caucho")),
    ("6403", ("cuero", "piel")),
    ("6404", ("deportiv", "zapatilla", "tela", "lona", "textil", "sneaker")),
    ("6406", ("parte", "suela", "plantilla", "talon", "cordon", "polaina")),
]


def resolve_taric(con, term: str) -> str | None:
    """Map a colloquial footwear term to a TARIC heading ('64xx'), or None."""
    t = (term or "").lower().strip()
    if not t:
        return None
    for heading, keywords in _HEADING_KEYWORDS:
        if any(k in t for k in keywords):
            return heading
    row = con.execute(
        "SELECT code FROM datacomex.taric_tree "
        "WHERE level IN (2, 4) AND lower(description) LIKE '%' || ? || '%' "
        "ORDER BY level DESC LIMIT 1",
        [t],
    ).fetchone()
    return row[0] if row else None


def filter_options(con) -> dict:
    """Values to populate the report page's selectors."""
    periods = [
        r[0] for r in con.execute(
            "SELECT DISTINCT period FROM datacomex.trade_flows ORDER BY period"
        ).fetchall()
    ]
    headings = [
        {"code": r[0], "description": r[1]}
        for r in con.execute(
            "SELECT code, description FROM datacomex.taric_tree "
            "WHERE level = 4 ORDER BY code"
        ).fetchall()
    ]
    countries = [
        r[0] for r in con.execute(
            "SELECT country_name FROM datacomex.trade_flows "
            "GROUP BY country_name ORDER BY SUM(value_eur) DESC LIMIT 15"
        ).fetchall()
    ]
    return {"periods": periods, "headings": headings, "countries": countries}


def evolution(con, *, flow: str, heading: str = "64", months: int = 24) -> dict:
    """Monthly value trend for a flow + TARIC scope, with a year-on-year KPI."""
    pred, param = _scope(heading)
    where = f"flow = ? AND {pred}"
    args = [flow, param]

    max_idx = con.execute(
        f"SELECT max(year * 12 + month) FROM datacomex.trade_flows WHERE {where}",
        args,
    ).fetchone()[0]

    rows = []
    if max_idx is not None:
        rows = con.execute(
            f"""
            SELECT period,
                   SUM(value_eur)           AS value_eur,
                   bool_or(is_provisional)  AS provisional
            FROM datacomex.trade_flows
            WHERE {where} AND year * 12 + month > ? - ?
            GROUP BY period
            ORDER BY period
            """,
            args + [max_idx, months],
        ).fetchall()

    periods = [r[0] for r in rows]
    values_m = [round(r[1] / 1e6, 2) for r in rows]
    provisional = any(r[2] for r in rows)

    def window_sum(lo: int, hi: int) -> float:
        if max_idx is None:
            return 0.0
        return con.execute(
            f"""SELECT COALESCE(SUM(value_eur), 0) FROM datacomex.trade_flows
                WHERE {where} AND year * 12 + month > ? AND year * 12 + month <= ?""",
            args + [max_idx - lo, max_idx - hi],
        ).fetchone()[0]

    trailing = window_sum(12, 0)
    prior = window_sum(24, 12)

    scope_label = "de calzado" if len(heading) <= 2 else f"(partida {heading})"
    return {
        "widget": "monthly_evolution",
        "title": f"{_FLOW_LABEL.get(flow, flow)} {scope_label} — últimos {months} meses",
        "echarts": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": periods},
            "yAxis": {"type": "value", "name": "M€"},
            "series": [
                {"name": "Valor", "type": "line", "smooth": True, "data": values_m}
            ],
        },
        "kpis": [_pct_kpi("Var. interanual", trailing, prior)],
        "meta": {
            "unit": "EUR",
            "granularity": "monthly",
            "is_provisional": provisional,
        },
    }


def country_ranking(
    con,
    *,
    flow: str,
    heading: str = "64",
    period_from: str | None = None,
    period_to: str | None = None,
    top_n: int = 10,
) -> dict:
    """Top partner countries by traded value for a flow + TARIC scope."""
    pred, param = _scope(heading)
    where = f"flow = ? AND {pred}"
    args: list = [flow, param]
    if period_from:
        where += " AND period >= ?"
        args.append(period_from)
    if period_to:
        where += " AND period <= ?"
        args.append(period_to)

    rows = con.execute(
        f"""
        SELECT country_name, SUM(value_eur) AS value_eur
        FROM datacomex.trade_flows
        WHERE {where}
        GROUP BY country_name
        ORDER BY value_eur DESC
        LIMIT ?
        """,
        args + [top_n],
    ).fetchall()

    total = con.execute(
        f"SELECT COALESCE(SUM(value_eur), 0) FROM datacomex.trade_flows WHERE {where}",
        args,
    ).fetchone()[0]

    # horizontal bar: ECharts draws the first category at the bottom, so reverse
    countries = [r[0] for r in rows][::-1]
    values_m = [round(r[1] / 1e6, 2) for r in rows][::-1]
    leader_share = (rows[0][1] / total * 100.0) if rows and total else 0.0

    scope_label = "de calzado" if len(heading) <= 2 else f"(partida {heading})"
    return {
        "widget": "country_ranking",
        "title": f"{_FLOW_LABEL.get(flow, flow)} {scope_label} por país (top {top_n})",
        "echarts": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "value", "name": "M€"},
            "yAxis": {"type": "category", "data": countries},
            "series": [{"name": "Valor", "type": "bar", "data": values_m}],
        },
        "kpis": [
            {"label": "Cuota del líder", "value": f"{leader_share:.1f}%", "tone": "neutral"}
        ],
        "meta": {"unit": "EUR", "granularity": "range"},
    }


def _period_range(where: str, args: list, period_from, period_to):
    if period_from:
        where += " AND period >= ?"
        args.append(period_from)
    if period_to:
        where += " AND period <= ?"
        args.append(period_to)
    return where, args


def product_mix(
    con, *, flow: str, period_from: str | None = None, period_to: str | None = None
) -> dict:
    """Share of traded value by TARIC heading (6401–6406) — a donut."""
    where, args = _period_range("flow = ? AND chapter = '64'", [flow], period_from, period_to)
    rows = con.execute(
        f"""SELECT heading, SUM(value_eur) FROM datacomex.trade_flows
            WHERE {where} GROUP BY heading ORDER BY heading""",
        args,
    ).fetchall()

    total = sum(r[1] for r in rows) or 0
    data = [
        {"name": SHORT_LABEL.get(h, h), "value": round(v / 1e6, 2)} for h, v in rows
    ]
    top_share = max((v for _, v in rows), default=0) / total * 100.0 if total else 0.0

    return {
        "widget": "product_mix",
        "title": f"{_FLOW_LABEL.get(flow, flow)} de calzado por tipo de producto",
        "echarts": {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} M€ ({d}%)"},
            "legend": {"bottom": 0},
            "series": [
                {
                    "type": "pie",
                    "radius": ["40%", "70%"],
                    "data": data,
                    "label": {"formatter": "{b}\n{d}%"},
                }
            ],
        },
        "kpis": [
            {"label": "Cuota del tipo dominante", "value": f"{top_share:.1f}%", "tone": "neutral"}
        ],
        "meta": {"unit": "EUR", "granularity": "range"},
    }


def avg_price(
    con,
    *,
    flow: str,
    heading: str = "64",
    country: str | None = None,
    months: int = 24,
) -> dict:
    """Implied unit price (€/kg) over time; null where a period has no weight."""
    pred, param = _scope(heading)
    where = f"flow = ? AND {pred}"
    args: list = [flow, param]
    if country:
        where += " AND country_name = ?"
        args.append(country)

    max_idx = con.execute(
        f"SELECT max(year * 12 + month) FROM datacomex.trade_flows WHERE {where}",
        args,
    ).fetchone()[0]

    rows = []
    if max_idx is not None:
        rows = con.execute(
            f"""
            SELECT period,
                   SUM(value_eur)  AS v,
                   SUM(weight_kg)  AS w
            FROM datacomex.trade_flows
            WHERE {where} AND year * 12 + month > ? - ?
            GROUP BY period ORDER BY period
            """,
            args + [max_idx, months],
        ).fetchall()

    periods = [r[0] for r in rows]
    prices = [round(r[1] / r[2], 2) if r[2] else None for r in rows]

    priced = [p for p in prices if p is not None]
    kpi = _pct_kpi(
        "Var. precio (12m)",
        priced[-1] if priced else 0.0,
        priced[0] if len(priced) > 1 else 0.0,
    )

    return {
        "widget": "avg_price",
        "title": f"Precio medio {_FLOW_LABEL.get(flow, flow).lower()} de calzado (€/kg)",
        "echarts": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": periods},
            "yAxis": {"type": "value", "name": "€/kg"},
            "series": [
                {"name": "€/kg", "type": "line", "smooth": True, "connectNulls": False,
                 "data": prices}
            ],
        },
        "kpis": [kpi],
        "meta": {"unit": "EUR/kg", "granularity": "monthly"},
    }


def balance(con, *, heading: str = "64", months: int = 24) -> dict:
    """Monthly trade balance (exports − imports) plus its running total."""
    pred, param = _scope(heading)
    where = pred
    args: list = [param]

    max_idx = con.execute(
        f"SELECT max(year * 12 + month) FROM datacomex.trade_flows WHERE {where}",
        args,
    ).fetchone()[0]

    rows = []
    if max_idx is not None:
        rows = con.execute(
            f"""
            SELECT period,
                   SUM(CASE WHEN flow = 'EXPORT' THEN value_eur ELSE -value_eur END) AS saldo
            FROM datacomex.trade_flows
            WHERE {where} AND year * 12 + month > ? - ?
            GROUP BY period ORDER BY period
            """,
            args + [max_idx, months],
        ).fetchall()

    periods = [r[0] for r in rows]
    saldo = [round(r[1] / 1e6, 2) for r in rows]
    cumulative, running = [], 0.0
    for s in saldo:
        running = round(running + s, 2)
        cumulative.append(running)

    total = cumulative[-1] if cumulative else 0.0
    tone = "positive" if total > 0 else "negative" if total < 0 else "neutral"

    return {
        "widget": "trade_balance",
        "title": "Saldo comercial de calzado (M€)",
        "echarts": {
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 0},
            "xAxis": {"type": "category", "data": periods},
            "yAxis": {"type": "value", "name": "M€"},
            "series": [
                {"name": "Saldo", "type": "bar", "data": saldo},
                {"name": "Acumulado", "type": "line", "smooth": True, "data": cumulative},
            ],
        },
        "kpis": [
            {"label": "Saldo acumulado", "value": f"{total:+.1f} M€", "tone": tone}
        ],
        "meta": {"unit": "EUR", "granularity": "monthly"},
    }
