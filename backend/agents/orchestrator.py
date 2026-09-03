from __future__ import annotations

import json
import time

from backend import events
from backend.agents import llm
from backend.agents.data_agent import answer_data_question
from backend.config import LLM_MODEL, MAX_TOKENS

_SYSTEM = """\
You are an analytics orchestrator. You have a data analyst subordinate you reach
via the query_data tool. Your job:
1. Turn the user's question into one or more precise data questions and call query_data.
2. Read the returned columns/rows.
3. Explain the finding in 1-3 short sentences of prose.
4. Design an appropriate Vega-Lite v5 chart for the returned data.

Call query_data at least once before answering. Do not invent numbers.
"""

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
        "vega_lite_spec": {"type": "object", "additionalProperties": True},
    },
    "required": ["answer", "chart_title", "chart_meta", "vega_lite_spec"],
    "additionalProperties": False,
}


class SpecError(ValueError):
    """Raised when the model's Vega-Lite spec is structurally invalid."""


def rows_to_records(columns: list[str], rows: list[list]) -> list[dict]:
    return [dict(zip(columns, r)) for r in rows]


def validate_vega_lite(spec: dict, rows_records: list[dict]) -> dict:
    if not isinstance(spec, dict):
        raise SpecError("spec is not an object")
    schema_url = str(spec.get("$schema", ""))
    if "vega-lite" not in schema_url:
        raise SpecError("spec is missing a Vega-Lite $schema")
    if "mark" not in spec and "layer" not in spec:
        raise SpecError("spec has neither 'mark' nor 'layer'")
    has_encoding = "encoding" in spec or any(
        "encoding" in layer for layer in spec.get("layer", []) if isinstance(layer, dict)
    )
    if not has_encoding:
        raise SpecError("spec has no 'encoding'")

    spec = json.loads(json.dumps(spec))  # deep copy
    data = spec.get("data")
    unbound = (
        data is None
        or (isinstance(data, dict) and not data.get("values"))
    )
    if unbound:
        spec["data"] = {"values": rows_records}
    spec.setdefault("width", "container")
    return spec


def run(user_message: str, sink: llm.Sink, *, data_fn=answer_data_question) -> None:
    started = time.monotonic()
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
        messages=[{"role": "user", "content": user_message}],
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

    close_out = llm.get_client().messages.create(
        model=LLM_MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM,
        messages=agent.messages
        + [
            {
                "role": "user",
                "content": "Now produce your final answer and Vega-Lite v5 spec "
                "for this dataset (leave data unbound; it will be injected):\n"
                + json.dumps({"columns": dataset.columns, "rows": dataset.rows[:50]}),
            }
        ],
        tools=[_QUERY_DATA_TOOL],
        output_config={"format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA}},
    )
    text = next(b.text for b in close_out.content if b.type == "text")
    payload = json.loads(text)

    sink(events.Step(label="chart.render", detail="vega-lite v5"))
    try:
        spec = validate_vega_lite(payload["vega_lite_spec"], records)
    except SpecError as exc:
        sink(events.Text(text=payload.get("answer", "")))
        sink(events.ErrorEvent(message=f"Invalid Vega-Lite spec: {exc}"))
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
