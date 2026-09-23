"""Componentes de calzado (Bloque A) — TARIC 8 dígitos, comercio de España.

Same DataComex source and chartSpec conventions as services/footwear.py, but
scoped over datacomex.component_flows (materias primas/insumos) instead of
calzado terminado. Kept as a separate module because the two domains use
different keys (partida vs. heading/chapter) and have no suppl_units.
"""
from __future__ import annotations

from projects.footwear.warehouse.schema import COMPONENT_PARTIDAS

_FLOW_LABEL = {"IMPORT": "Importaciones", "EXPORT": "Exportaciones"}


def _scope(partida: str) -> tuple[str, str]:
    """(sql predicate, param) for all components ('ALL') or one partida."""
    partida = (partida or "ALL").strip()
    if partida in ("ALL", "", "64"):
        return "1 = 1", None
    return "partida = ?", partida


def _chart_type(requested: str | None, allowed: set[str], default: str) -> str:
    return requested if requested in allowed else default


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


def _partida_label(partida: str) -> str:
    partida = (partida or "ALL").strip()
    if partida in ("ALL", "", "64"):
        return "de componentes de calzado"
    desc = COMPONENT_PARTIDAS.get(partida, partida)
    return f"(partida {partida} — {desc})"


def filter_options(con) -> dict:
    """Partida list to populate the report page's selector."""
    return {
        "partidas": [
            {"code": code, "description": desc}
            for code, desc in sorted(COMPONENT_PARTIDAS.items())
        ]
    }


def evolution(
    con, *, flow: str, partida: str = "ALL", months: int = 24,
    chart_type: str | None = None,
) -> dict:
    """Monthly value trend for a flow + partida scope, with a YoY KPI."""
    series_type = _chart_type(chart_type, {"line", "bar"}, "line")
    pred, param = _scope(partida)
    where = f"flow = ? AND {pred}"
    args = [flow] + ([param] if param is not None else [])

    max_idx = con.execute(
        f"SELECT max(year * 12 + month) FROM datacomex.component_flows WHERE {where}",
        args,
    ).fetchone()[0]

    rows = []
    if max_idx is not None:
        rows = con.execute(
            f"""
            SELECT period,
                   SUM(value_eur)           AS value_eur,
                   bool_or(is_provisional)  AS provisional
            FROM datacomex.component_flows
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
            f"""SELECT COALESCE(SUM(value_eur), 0) FROM datacomex.component_flows
                WHERE {where} AND year * 12 + month > ? AND year * 12 + month <= ?""",
            args + [max_idx - lo, max_idx - hi],
        ).fetchone()[0]

    trailing = window_sum(12, 0)
    prior = window_sum(24, 12)

    return {
        "widget": "component_evolution",
        "title": f"{_FLOW_LABEL.get(flow, flow)} {_partida_label(partida)} — últimos {months} meses",
        "echarts": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": periods},
            "yAxis": {"type": "value", "name": "M€"},
            "series": [
                {"name": "Valor", "type": series_type, "smooth": True, "data": values_m}
            ],
        },
        "kpis": [_pct_kpi("Var. interanual", trailing, prior)],
        "meta": {
            "unit": "EUR",
            "granularity": "monthly",
            "notes": (["incluye datos provisionales"] if provisional else []),
        },
    }


def country_ranking(
    con,
    *,
    flow: str,
    partida: str = "ALL",
    top_n: int = 10,
    chart_type: str | None = None,
) -> dict:
    """Top partner countries by value for a flow + partida scope.

    Also surfaces the leader's share, so a single-country dependency on a
    critical component (risk-of-supply signal) is visible without a
    separate widget.
    """
    series_type = _chart_type(chart_type, {"bar", "pie"}, "bar")
    pred, param = _scope(partida)
    where = f"flow = ? AND {pred}"
    args: list = [flow] + ([param] if param is not None else [])

    rows = con.execute(
        f"""
        SELECT country_name, SUM(value_eur) AS value_eur
        FROM datacomex.component_flows
        WHERE {where}
        GROUP BY country_name
        ORDER BY value_eur DESC
        LIMIT ?
        """,
        args + [top_n],
    ).fetchall()

    total = con.execute(
        f"SELECT COALESCE(SUM(value_eur), 0) FROM datacomex.component_flows WHERE {where}",
        args,
    ).fetchone()[0]

    # horizontal bar: ECharts draws the first category at the bottom, so reverse
    countries = [r[0] for r in rows][::-1]
    values_m = [round(r[1] / 1e6, 2) for r in rows][::-1]
    leader_share = (rows[0][1] / total * 100.0) if rows and total else 0.0

    if series_type == "pie":
        echarts = {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} M€ ({d}%)"},
            "legend": {"bottom": 0},
            "series": [
                {
                    "type": "pie",
                    "radius": ["40%", "70%"],
                    "data": [
                        {"name": c, "value": v}
                        for c, v in zip(countries[::-1], values_m[::-1])
                    ],
                }
            ],
        }
    else:
        echarts = {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "value", "name": "M€"},
            "yAxis": {"type": "category", "data": countries},
            "series": [{"name": "Valor", "type": "bar", "data": values_m}],
        }

    tone = "negative" if leader_share >= 60 else "neutral"
    return {
        "widget": "component_country_ranking",
        "title": f"{_FLOW_LABEL.get(flow, flow)} {_partida_label(partida)} por país (top {top_n})",
        "echarts": echarts,
        "kpis": [
            {"label": "Cuota del líder", "value": f"{leader_share:.1f}%", "tone": tone}
        ],
        "meta": {"unit": "EUR", "granularity": "range", "notes": []},
    }


def balance(
    con, *, partida: str = "ALL", months: int = 24, chart_type: str | None = None,
) -> dict:
    """Monthly trade balance (exports − imports) plus its running total."""
    series_type = _chart_type(chart_type, {"bar", "line"}, "bar")
    pred, param = _scope(partida)
    where = pred
    args: list = [param] if param is not None else []

    max_idx = con.execute(
        f"SELECT max(year * 12 + month) FROM datacomex.component_flows WHERE {where}",
        args,
    ).fetchone()[0]

    rows = []
    if max_idx is not None:
        rows = con.execute(
            f"""
            SELECT period,
                   SUM(CASE WHEN flow = 'EXPORT' THEN value_eur ELSE -value_eur END) AS saldo
            FROM datacomex.component_flows
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
        "widget": "component_trade_balance",
        "title": f"Saldo comercial {_partida_label(partida)} (M€)",
        "echarts": {
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 0},
            "xAxis": {"type": "category", "data": periods},
            "yAxis": {"type": "value", "name": "M€"},
            "series": [
                {"name": "Saldo", "type": series_type, "data": saldo},
                {"name": "Acumulado", "type": "line", "smooth": True, "data": cumulative},
            ],
        },
        "kpis": [
            {"label": "Saldo acumulado", "value": f"{total:+.1f} M€", "tone": tone}
        ],
        "meta": {"unit": "EUR", "granularity": "monthly", "notes": []},
    }
