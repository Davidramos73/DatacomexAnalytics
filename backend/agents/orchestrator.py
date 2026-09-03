from __future__ import annotations

import json
import time

from backend import events
from backend.agents import llm
from backend.agents.data_agent import answer_data_question
from backend.config import LLM_MODEL

_SYSTEM = """\
You are an analytics orchestrator. You have a data analyst subordinate you reach
via the query_data tool. Your job:
1. Turn the user's question into one or more precise data questions and call query_data.
2. Read the returned columns/rows.
3. Explain the finding in 1-3 short sentences of prose.
4. Design an appropriate Apache ECharts v5 `option` object for the returned data.

ECharts chart rules:
- Return a plain `option` object (the argument to `chart.setOption`).
- Leave the data unbound: do NOT put rows in `series[].data`. The rows are
  injected as `option.dataset.source` (an array of row objects keyed by column
  name); reference columns via each series' `encode` (e.g.
  {"x": "month", "y": "revenue"}) or, for pie, `encode: {"itemName": "region",
  "value": "rev"}`.
- Allowed series `type`: bar, line, pie, scatter.
- Include `xAxis`/`yAxis` for cartesian charts (omit for pie).
- Do NOT set colors, fonts, or a `backgroundColor` - the UI applies a theme.

Call query_data at least once before answering. Do not invent numbers.

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

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "chart_title": {"type": "string"},
        "chart_meta": {"type": "string"},
        "echarts_option": {
            "type": "string",
            "description": "The ECharts v5 option object as a JSON-encoded string.",
        },
    },
    "required": ["answer", "chart_title", "chart_meta", "echarts_option"],
    "additionalProperties": False,
}


class SpecError(ValueError):
    """Raised when the model's ECharts option is structurally invalid."""


def rows_to_records(columns: list[str], rows: list[list]) -> list[dict]:
    return [dict(zip(columns, r)) for r in rows]


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


def validate_echarts_option(option: dict, rows_records: list[dict]) -> dict:
    if not isinstance(option, dict):
        raise SpecError("option is not an object")
    series = option.get("series")
    if isinstance(series, dict):
        series = [series]
    if not series or not isinstance(series, list):
        raise SpecError("option has no 'series'")

    option = json.loads(json.dumps(option))  # deep copy
    # Bind the data unless the model already inlined a dataset.
    dataset = option.get("dataset")
    has_source = isinstance(dataset, dict) and dataset.get("source")
    if not has_source:
        option["dataset"] = {"source": rows_records}
    return option


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
        return json.dumps(
            {
                "sql": result.sql,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
            }
        )

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

    dataset = ok_datasets[-1]
    records = rows_to_records(dataset.columns, dataset.rows)

    payload = llm.structured_json(
        model=LLM_MODEL,
        system=_SYSTEM,
        messages=agent.messages
        + [
            {
                "role": "user",
                "content": "Now produce your final answer and ECharts v5 option "
                "for this dataset (leave data unbound; it will be injected):\n"
                + json.dumps({"columns": dataset.columns, "rows": dataset.rows[:50]}),
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

    if isinstance(payload.get("echarts_option"), str):
        try:
            payload["echarts_option"] = json.loads(payload["echarts_option"])
        except json.JSONDecodeError as exc:
            sink(events.Text(text=payload.get("answer", "")))
            sink(events.ErrorEvent(message=f"Invalid ECharts option: {exc}"))
            sink(events.Done(seconds=round(time.monotonic() - started, 1)))
            return

    sink(events.Step(label="chart.render", detail="echarts v5"))
    try:
        spec = validate_echarts_option(payload["echarts_option"], records)
    except SpecError as exc:
        sink(events.Text(text=payload.get("answer", "")))
        sink(events.ErrorEvent(message=f"Invalid ECharts option: {exc}"))
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
