from __future__ import annotations

from backend.services import footwear
from backend.widgets import Param, Widget, chart_type_param

REST_PREFIX = "/api/v1/reports/footwear"

_FLOW = Param(
    "flow", "enum", required=True, default="IMPORT", enum=["IMPORT", "EXPORT"],
    ui_label="Flujo",
    ui_options=[{"value": "IMPORT", "label": "Importaciones"},
                {"value": "EXPORT", "label": "Exportaciones"}],
)
_HEADING = Param(
    "heading", "str", default="64", ui_label="Partida",
    ui_options_from="headings", ui_option_label="{code} — {description}",
)
_MONTHS = Param("months", "int", default=24, ui_label="Meses")

WIDGETS: list[Widget] = [
    Widget(
        key="evolution", fn=footwear.evolution, rest_path="/evolution",
        tool_name="footwear_market_overview",
        tool_description=(
            "Evolución mensual del valor de importaciones/exportaciones de "
            "calzado, con variación interanual. Para 'tendencia', 'evolución'."
        ),
        params=[_FLOW, _HEADING, _MONTHS, chart_type_param(["line", "bar"])],
        chart_types=["line", "bar"], span="full",
    ),
    Widget(
        key="countries", fn=footwear.country_ranking, rest_path="/countries",
        tool_name="footwear_top_partners",
        tool_description=(
            "Ranking de países origen/destino por valor. Para 'de dónde "
            "importamos', 'a dónde exportamos', 'principales socios'."
        ),
        params=[_FLOW, _HEADING,
                Param("top_n", "int", default=10, ui_label="Top"),
                chart_type_param(["bar", "pie"])],
        chart_types=["bar", "pie"], span="full",
    ),
    Widget(
        key="mix", fn=footwear.product_mix, rest_path="/product-mix",
        tool_name="footwear_product_mix",
        tool_description=(
            "Reparto del valor por tipo de calzado (partidas 6401–6406)."
        ),
        params=[_FLOW, chart_type_param(["pie", "bar"])],
        chart_types=["pie", "bar"], span="half",
    ),
    Widget(
        key="price", fn=footwear.avg_price, rest_path="/avg-price",
        tool_name="footwear_avg_price",
        tool_description="Precio medio implícito en €/kg a lo largo del tiempo.",
        params=[_FLOW, _HEADING,
                Param("country", "str", ui_label="País"),
                _MONTHS, chart_type_param(["line", "bar"])],
        chart_types=["line", "bar"], span="half",
    ),
    Widget(
        key="balance", fn=footwear.balance, rest_path="/balance",
        tool_name="footwear_trade_balance",
        tool_description=(
            "Saldo comercial mensual (exportaciones − importaciones) y acumulado."
        ),
        params=[_HEADING, _MONTHS, chart_type_param(["bar", "line"])],
        chart_types=["bar", "line"], span="full",
    ),
]
