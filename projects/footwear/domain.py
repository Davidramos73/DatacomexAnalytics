"""FootwearDomain — the Analista de Calzado implementation of the Domain protocol.

Spanish content ported from backend/agents/orchestrator_footwear.py and
frontend/index.html.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

import chatkit.config as config
from chatkit import events
from chatkit.domain import AppConfig, Branding, TabDescriptor, default_finalize
from projects.footwear.services import footwear
from projects.footwear.services.widgets import REST_PREFIX, WIDGETS

_SYSTEM = """\
Eres analista de comercio exterior de la industria española del calzado. Respondes
preguntas sobre importaciones y exportaciones de calzado (capítulo TARIC 64) con
datos de DataComex, mediante un conjunto reducido de herramientas.

Reglas:
- Si el usuario nombra un producto de forma coloquial ("deportivas", "botas de
  agua", "de cuero"...), llama PRIMERO a resolve_footwear_product para obtener la
  partida, y pásala como `heading` a la herramienta de informe.
- Llama a EXACTAMENTE UNA herramienta de informe que responda a la pregunta:
  footwear_market_overview (tendencia), footwear_top_partners (ranking),
  footwear_product_mix, footwear_avg_price, footwear_trade_balance.
- No llames herramientas que no necesitas. En cuanto un informe responde, para.
- Cada herramienta de informe SÍ genera un gráfico real (se muestra al usuario
  junto a tu respuesta) y acepta un parámetro `chart_type` para elegir el
  formato entre los que admite esa herramienta (ver su descripción). Si el
  usuario pide un formato distinto ("en barras", "como torta"...) para la
  misma pregunta, vuelve a llamar la MISMA herramienta con ese `chart_type` —
  nunca respondas que no puedes generar gráficos.
- Si los datos incluyen el último periodo, son provisionales: menciónalo.
- Responde en 1-3 frases de prosa en español. Nunca inventes cifras.
"""

_CLOSEOUT = (
    "Resume el hallazgo en 1-3 frases de prosa en español. "
    "Sin JSON, sin markdown, sin gráfico."
)

_FLOW_LABEL = {"IMPORT": "Importación", "EXPORT": "Exportación"}

_STEP_TITLES = {
    "footwear_market_overview": "Analizando la evolución del comercio",
    "footwear_top_partners": "Calculando el ranking de países",
    "footwear_product_mix": "Desglosando el mix de producto",
    "footwear_avg_price": "Calculando el precio medio",
    "footwear_trade_balance": "Calculando la balanza comercial",
}

_RESOLVE_DEF = {
    "name": "resolve_footwear_product",
    "description": (
        "Traduce un tipo de calzado en lenguaje natural (p. ej. 'deportivas', "
        "'botas de agua', 'de cuero') a su partida TARIC de 4 dígitos. "
        "LLÁMALO SIEMPRE primero si el usuario usa términos coloquiales de producto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"term": {"type": "string"}},
        "required": ["term"],
        "additionalProperties": False,
    },
}

_PROMPTS = [
    "¿Cómo ha evolucionado la importación de calzado en los últimos 2 años?",
    "Muéstrame la evolución de las exportaciones de calzado de cuero desde 2020",
    "¿Quiénes son los principales países de origen de las importaciones de calzado?",
    "¿A qué países exportamos más calzado?",
    "Top 10 proveedores de calzado deportivo",
    "¿Qué tipo de calzado importamos más, deportivo o de cuero?",
    "¿Cuál es el precio medio por kilo del calzado que importamos de China?",
    "¿Ha subido el precio medio del calzado de cuero en el último año?",
    "¿Cuál es la balanza comercial de calzado de España?",
    "¿Cuánto calzado deportivo importamos de Vietnam?",
]

_COPY = {
    "empty_title": "¿Qué miramos del calzado?",
    "empty_text": (
        "Pregunta por importaciones, exportaciones, socios comerciales, "
        "mix de producto o precios de calzado."
    ),
    "placeholder": "Pregunta sobre el calzado…",
    "hint_html": (
        "Respuestas generadas por IA a partir de datos oficiales "
        "DataComex (cap. 64, calzado) · pueden contener errores, verifica "
        'cifras críticas · <a href="#" data-role="hint-tab">ver panel de '
        "reportes</a>"
    ),
}

_THEMES = [
    "lumen", "default", "macarons", "vintage", "westeros",
    "roma", "shine", "walden", "chalk", "dark",
]


class FootwearDomain:
    settings = config
    system_prompt = _SYSTEM
    prose_closeout_instruction = _CLOSEOUT

    def app_config(self) -> AppConfig:
        return AppConfig(
            branding=Branding(
                "Analista de Calzado",
                "Calzado · DataComex",
                "DataComex · TARIC 64",
                "🥾",
            ),
            example_prompts=list(_PROMPTS),
            echarts_themes=list(_THEMES),
            tabs=[
                TabDescriptor(
                    "reports", "Panel de reportes", "bars", "widget_grid",
                    widgets=["evolution", "countries", "mix", "price", "balance"],
                    filters=["flow", "heading", "months"],
                )
            ],
            copy=dict(_COPY),
        )

    def open_connection(self):
        return duckdb.connect(str(config.DATACOMEX_PATH), read_only=True)

    def widgets(self):
        return WIDGETS

    def extra_tools(self) -> dict:
        def resolve_footwear_product(term: str) -> str:
            con = self.open_connection()
            try:
                return json.dumps({"heading": footwear.resolve_taric(con, term)})
            finally:
                con.close()

        return {
            "defs": [_RESOLVE_DEF],
            "handlers": {"resolve_footwear_product": resolve_footwear_product},
        }

    def web_dir(self) -> str:
        return str(Path(__file__).parent / "web")

    def finalize(self, agent, con) -> dict | None:
        return default_finalize(
            agent, con, report_tool_names={w.tool_name for w in WIDGETS}
        )

    def step_label(self, name: str, tool_input: dict) -> events.Step | None:
        if name == "resolve_footwear_product":
            term = tool_input.get("term", "")
            return events.Step(
                label="Identificando el producto",
                detail=f"«{term}»" if term else None,
            )

        label = _STEP_TITLES.get(name, name)
        bits = []
        flow = tool_input.get("flow")
        if flow:
            bits.append(_FLOW_LABEL.get(flow, flow))
        heading = tool_input.get("heading")
        if heading and heading != "64":
            bits.append(f"partida {heading}")
        if tool_input.get("top_n"):
            bits.append(f"top {tool_input['top_n']}")
        if tool_input.get("country"):
            bits.append(tool_input["country"])
        if tool_input.get("months"):
            bits.append(f"{tool_input['months']} meses")
        return events.Step(label=label, detail=" · ".join(bits) or None)

    def report_prefix(self) -> str:
        return REST_PREFIX

    def filter_options(self, con) -> dict:
        return footwear.filter_options(con)
