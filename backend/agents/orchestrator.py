from __future__ import annotations

import json
import time

from backend import charts, events
from backend.agents import llm
from backend.agents.data_agent import answer_data_question
from backend.config import LLM_MODEL

_SYSTEM = """\
You are an analytics orchestrator. You have a data analyst subordinate you reach
via the query_data tool. Your job:
1. Turn the user's question into one or more precise data questions and call query_data.
2. Read the returned columns/rows.
3. Explain the finding in 1-3 short sentences of prose.
4. Choose how to chart the result: chart_type (bar, line, pie or scatter),
   chart_x (the category / x-axis column), chart_y (an array of one or more
   numeric columns), and chart_series_by (a column to split into multiple
   series, or null). Use the exact column names returned by the query. The UI
   builds and styles the actual chart.

Call query_data as few times as possible - almost always exactly ONCE. As
soon as one result answers the user's question, STOP calling tools and give
your final answer. Do NOT re-query to reformat, to "double-check", or to add
columns you do not need. Never invent numbers.

Earlier turns of this conversation may be provided for context. The user's
latest message can build on them (e.g. "now break that down by month" or
"same thing for EMEA") - resolve such references before writing data questions.
"""

MAX_HISTORY_TURNS = 6

_QUERY_DATA_TOOL = {
    "name": "query_data",
    "description": "Ask the data analyst a natural-language question about the warehouse. "
    "Returns JSON with sql, columns, rows, row_count.",
    "input_schema": {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
        "additionalProperties": False,
    },
}

# Flat, no nested objects — models follow this far more reliably in JSON mode.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "chart_title": {"type": "string"},
        "chart_meta": {"type": "string"},
        "chart_type": {"type": "string", "enum": list(charts.ALLOWED_TYPES)},
        "chart_x": {
            "type": "string",
            "description": "result column for the category / x axis (pie slice label)",
        },
        "chart_y": {
            "type": "array",
            "items": {"type": "string"},
            "description": "one or more numeric result columns for the y axis / pie value",
        },
        "chart_series_by": {
            "type": ["string", "null"],
            "description": "result column to split into multiple series, or null",
        },
    },
    "required": [
        "answer", "chart_title", "chart_meta",
        "chart_type", "chart_x", "chart_y", "chart_series_by",
    ],
    "additionalProperties": False,
}


def rows_to_records(columns: list[str], rows: list[list]) -> list[dict]:
    return [dict(zip(columns, r)) for r in rows]


def _chartability(dataset) -> tuple:
    """Rough score for how chartable a data-agent result is: needs rows and at
    least one numeric column. A 1-row MIN/MAX diagnostic scores near zero."""
    rows = min(dataset.row_count, 50)
    records = [dict(zip(dataset.columns, r)) for r in dataset.rows[:20]]
    has_numeric = any(charts._is_numeric(records, c) for c in dataset.columns)
    return (rows if has_numeric else 0, rows)


def clean_history(turns) -> list[dict]:
    """Coerce client-supplied turns into a valid alternating message list:
    only user/assistant roles, non-empty, no consecutive same-role, starts
    with a user turn, capped to the most recent MAX_HISTORY_TURNS."""
    out: list[dict] = []
    for t in turns or []:
        role = t.get("role")
        content = (t.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if out and out[-1]["role"] == role:
            out[-1] = {"role": role, "content": content}
        else:
            out.append({"role": role, "content": content})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out[-MAX_HISTORY_TURNS:]


def run(
    user_message: str,
    sink: llm.Sink,
    *,
    history=None,
    data_fn=answer_data_question,
) -> None:
    started = time.monotonic()
    prior = clean_history(history)
    sink(events.Thinking(label="Reading schema"))

    datasets: list = []

    def _query_data(question: str) -> str:
        result = data_fn(question, sink)
        datasets.append(result)
        if not result.ok:
            return json.dumps({"error": result.error})
        payload = {
            "sql": result.sql,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }
        # Weaker models keep re-querying; make "you're done" explicit.
        ok_so_far = sum(1 for d in datasets if d.ok)
        if ok_so_far == 1:
            payload["note"] = (
                "This answers the question. Do NOT call query_data again - "
                "give your final answer now."
            )
        else:
            payload["note"] = (
                "Stop calling query_data. Answer now using the data you have."
            )
        return json.dumps(payload)

    agent = llm.run_agent(
        model=LLM_MODEL,
        system=_SYSTEM,
        messages=prior + [{"role": "user", "content": user_message}],
        tools=[_QUERY_DATA_TOOL],
        tool_impls={"query_data": _query_data},
        sink=sink,
        step_label=lambda name, inp: events.Step(
            label="query_data", detail=inp.get("question", "")
        ),
    )

    ok_datasets = [d for d in datasets if d.ok]
    if not ok_datasets:
        msg = datasets[-1].error if datasets else "the data agent returned nothing"
        sink(events.ErrorEvent(message=f"No data available: {msg}"))
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
        return

    # A model that over-explores often ends on a 1-row diagnostic query; chart
    # its most chartable result (rows + a numeric column), latest wins on a tie.
    dataset = max(
        enumerate(ok_datasets),
        key=lambda t: (_chartability(t[1]), t[0]),
    )[1]

    payload = llm.structured_json(
        model=LLM_MODEL,
        system=_SYSTEM,
        messages=agent.messages
        + [
            {
                "role": "user",
                "content": (
                    "Now give your final answer and the chart mapping. This is the "
                    "ONLY result being charted - chart_x, chart_y and chart_series_by "
                    "must be exact column names from it; ignore columns from any "
                    "earlier query.\n"
                    f"columns: {dataset.columns}\n"
                    + json.dumps({"rows": dataset.rows[:50]})
                ),
            }
        ],
        tools=[_QUERY_DATA_TOOL],
        schema=_RESPONSE_SCHEMA,
        schema_name="chart_response",
    )
    # Some models return these as objects/numbers; the UI wants plain strings.
    for key in ("answer", "chart_title", "chart_meta"):
        val = payload.get(key)
        if val is None:
            payload[key] = ""
        elif not isinstance(val, str):
            payload[key] = json.dumps(val) if isinstance(val, (dict, list)) else str(val)

    chart = {
        "chart_type": payload.get("chart_type"),
        "x": payload.get("chart_x"),
        "y": payload.get("chart_y"),
        "series_by": payload.get("chart_series_by"),
    }

    sink(events.Step(label="chart.render", detail="echarts v5"))
    try:
        spec = charts.build_option(chart, dataset.columns, dataset.rows)
    except charts.ChartError as exc:
        sink(events.Text(text=payload.get("answer", "")))
        sink(events.ErrorEvent(message=f"Could not build chart: {exc}"))
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
        return

    sink(events.Text(text=payload["answer"]))
    sink(
        events.Chart(
            title=payload["chart_title"],
            meta=payload["chart_meta"],
            spec=spec,
            data={"columns": dataset.columns, "rows": dataset.rows},
        )
    )
    sink(events.Done(seconds=round(time.monotonic() - started, 1)))
