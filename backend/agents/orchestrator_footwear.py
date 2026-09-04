"""Footwear (DataComex) chat orchestrator.

The agent picks a domain tool; each report tool returns a ready-made ECharts
option, so there is no free SQL and no chart-mapping close-out — we stream the
prose and hand the tool's `echarts` straight to the UI.
"""
from __future__ import annotations

import json
import time

import duckdb

import backend.config as config
from backend import events
from backend.agents import llm, tools_footwear
from backend.agents.orchestrator import clean_history
from backend.config import LLM_MODEL

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
- Si los datos incluyen el último periodo, son provisionales: menciónalo.
- Responde en 1-3 frases de prosa en español. Nunca inventes cifras.
"""


def _default_con():
    return duckdb.connect(str(config.DATACOMEX_PATH), read_only=True)


_FLOW_LABEL = {"IMPORT": "Importación", "EXPORT": "Exportación"}

_STEP_TITLES = {
    "footwear_market_overview": "Analizando la evolución del comercio",
    "footwear_top_partners": "Calculando el ranking de países",
    "footwear_product_mix": "Desglosando el mix de producto",
    "footwear_avg_price": "Calculando el precio medio",
    "footwear_trade_balance": "Calculando la balanza comercial",
}


def _step_label(name: str, tool_input: dict) -> events.Step:
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


def _last_report(tool_calls) -> dict | None:
    for tc in reversed(tool_calls):
        if tc.name in tools_footwear.REPORT_TOOLS and not tc.is_error:
            try:
                return json.loads(tc.result)
            except (json.JSONDecodeError, TypeError):
                return None
    return None


def _meta_line(report: dict) -> str:
    parts = [f"{k['label']}: {k['value']}" for k in report.get("kpis", [])]
    if report.get("meta", {}).get("is_provisional"):
        parts.append("incluye datos provisionales")
    return " · ".join(parts)


def run(user_message: str, sink, *, history=None, con_factory=None) -> None:
    started = time.monotonic()
    con = (con_factory or _default_con)()
    try:
        prior = clean_history(history)
        sink(events.Thinking(label="Consultando DataComex"))

        agent = llm.run_agent(
            model=LLM_MODEL,
            system=_SYSTEM,
            messages=prior + [{"role": "user", "content": user_message}],
            tools=tools_footwear.tool_defs(),
            tool_impls=tools_footwear.handlers(con),
            sink=sink,
            step_label=_step_label,
        )

        report = _last_report(agent.tool_calls)
        if report is None:
            sink(events.Text(
                text=agent.final_text
                or "No pude generar un informe para esa consulta."
            ))
            sink(events.Done(seconds=round(time.monotonic() - started, 1)))
            return

        answer = ""
        for piece in llm.stream_text(
            model=LLM_MODEL,
            system=_SYSTEM,
            messages=agent.messages
            + [
                {
                    "role": "user",
                    "content": "Resume el hallazgo en 1-3 frases de prosa en español. "
                    "Sin JSON, sin markdown, sin gráfico.",
                }
            ],
        ):
            answer += piece
            sink(events.Delta(text=piece))
        answer = answer.strip()

        sink(events.Step(label="chart.render", detail="echarts v5"))
        sink(events.Text(text=answer))
        sink(
            events.Chart(
                title=report.get("title", "Informe"),
                meta=_meta_line(report),
                spec=report["echarts"],
                data={"columns": [], "rows": []},
            )
        )
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
    finally:
        con.close()
