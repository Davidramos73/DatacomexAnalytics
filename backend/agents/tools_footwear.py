"""Agent tools for the footwear (DataComex) domain.

Thin wrappers over `backend.services.footwear`. Handlers return the JSON
string of a chartSpec envelope `{widget, title, echarts, kpis, meta}`, the
same shape the REST report endpoints return — so the chat and the reports
page never diverge, and the orchestrator can hand `echarts` straight to the UI.
"""
from __future__ import annotations

import json

from backend.services import footwear

REPORT_TOOLS = {
    "footwear_market_overview",
    "footwear_top_partners",
    "footwear_product_mix",
    "footwear_avg_price",
    "footwear_trade_balance",
}

_FLOW = {
    "type": "string",
    "enum": ["IMPORT", "EXPORT"],
    "description": "IMPORT (importaciones) o EXPORT (exportaciones)",
}
_HEADING = {
    "type": "string",
    "description": "Partida TARIC '64xx' (o '64' para todo el calzado). "
    "Usa resolve_footwear_product para obtenerla de un término coloquial.",
}
_MONTHS = {"type": "integer", "description": "Meses hacia atrás (por defecto 24)"}


def _chart_type_field(options: str, default: str) -> dict:
    return {
        "type": "string",
        "enum": options.split("|"),
        "description": f"Tipo de gráfico ({options}). Por defecto {default}. "
        "Úsalo si el usuario pide explícitamente otro formato.",
    }


def tool_defs() -> list[dict]:
    return [
        {
            "name": "resolve_footwear_product",
            "description": "Traduce un tipo de calzado descrito en lenguaje natural "
            "(p. ej. 'deportivas', 'botas de agua', 'de cuero') a su partida TARIC "
            "de 4 dígitos. LLÁMALO SIEMPRE primero si el usuario usa términos "
            "coloquiales de producto.",
            "input_schema": {
                "type": "object",
                "properties": {"term": {"type": "string"}},
                "required": ["term"],
                "additionalProperties": False,
            },
        },
        {
            "name": "footwear_market_overview",
            "description": "Evolución mensual del valor de importaciones/exportaciones "
            "de calzado, con variación interanual. Para 'tendencia', 'evolución', "
            "'cómo va'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "flow": _FLOW, "heading": _HEADING, "months": _MONTHS,
                    "chart_type": _chart_type_field("line|bar", "line"),
                },
                "required": ["flow"],
                "additionalProperties": False,
            },
        },
        {
            "name": "footwear_top_partners",
            "description": "Ranking de países origen/destino por valor. Para "
            "'de dónde importamos', 'a dónde exportamos', 'principales socios'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "flow": _FLOW,
                    "heading": _HEADING,
                    "top_n": {"type": "integer", "description": "por defecto 10"},
                    "chart_type": _chart_type_field("bar|pie", "bar"),
                },
                "required": ["flow"],
                "additionalProperties": False,
            },
        },
        {
            "name": "footwear_product_mix",
            "description": "Reparto del valor por tipo de calzado (partidas 6401–6406). "
            "Para 'qué tipo de calzado', 'mix de producto'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "flow": _FLOW,
                    "chart_type": _chart_type_field("pie|bar", "pie"),
                },
                "required": ["flow"],
                "additionalProperties": False,
            },
        },
        {
            "name": "footwear_avg_price",
            "description": "Precio medio implícito en €/kg a lo largo del tiempo. "
            "Para 'precio', 'valor por kilo', 'se encarece'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "flow": _FLOW,
                    "heading": _HEADING,
                    "country": {"type": "string"},
                    "months": _MONTHS,
                    "chart_type": _chart_type_field("line|bar", "line"),
                },
                "required": ["flow"],
                "additionalProperties": False,
            },
        },
        {
            "name": "footwear_trade_balance",
            "description": "Saldo comercial mensual (exportaciones − importaciones) y "
            "acumulado. Para 'balanza', 'saldo', 'déficit/superávit'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "heading": _HEADING, "months": _MONTHS,
                    "chart_type": _chart_type_field("bar|line", "bar"),
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    ]


def handlers(con) -> dict:
    def _dump(d) -> str:
        return json.dumps(d)

    return {
        "resolve_footwear_product": lambda term: _dump(
            {"heading": footwear.resolve_taric(con, term)}
        ),
        "footwear_market_overview": lambda flow, heading="64", months=24,
        chart_type=None: _dump(
            footwear.evolution(
                con, flow=flow.upper(), heading=heading, months=int(months),
                chart_type=chart_type,
            )
        ),
        "footwear_top_partners": lambda flow, heading="64", top_n=10,
        chart_type=None: _dump(
            footwear.country_ranking(
                con, flow=flow.upper(), heading=heading, top_n=int(top_n),
                chart_type=chart_type,
            )
        ),
        "footwear_product_mix": lambda flow, chart_type=None: _dump(
            footwear.product_mix(con, flow=flow.upper(), chart_type=chart_type)
        ),
        "footwear_avg_price": lambda flow, heading="64", country=None, months=24,
        chart_type=None: _dump(
            footwear.avg_price(
                con, flow=flow.upper(), heading=heading, country=country,
                months=int(months), chart_type=chart_type,
            )
        ),
        "footwear_trade_balance": lambda heading="64", months=24, chart_type=None: _dump(
            footwear.balance(con, heading=heading, months=int(months),
                              chart_type=chart_type)
        ),
    }
