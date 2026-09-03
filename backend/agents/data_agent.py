from __future__ import annotations

import dataclasses
import json

from backend import events
from backend.agents import llm
from backend.config import DATA_AGENT_MODEL
from backend.warehouse import db, schema

_SYSTEM = """\
You are a senior data analyst with read-only access to a small analytics warehouse.
Given a question, write ONE SQL SELECT that answers it, run it with the run_sql tool,
and then briefly state what the data shows.

{schema}

Guidance:
- Call get_schema only if you need to re-check column names.
- Prefer a single GROUP BY aggregation. Alias output columns in friendly snake_case.
- Keep result sets small (a handful of rows is ideal for charting).
- If run_sql returns an error, fix the SQL and try again.
"""

_TOOLS = [
    {
        "name": "get_schema",
        "description": "Return the warehouse schema, business notes and sample rows.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_sql",
        "description": "Execute a read-only SQL SELECT against the warehouse and return columns + rows as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
]


@dataclasses.dataclass
class DataResult:
    ok: bool
    sql: str = ""
    columns: list = dataclasses.field(default_factory=list)
    rows: list = dataclasses.field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    notes: str = ""
    error: str = ""


def _step_label(name: str, tool_input: dict) -> events.Step:
    if name == "run_sql":
        return events.Step(label="sql.query", detail=tool_input.get("sql", ""))
    if name == "get_schema":
        return events.Step(label="schema.lookup")
    return events.Step(label=name)


def answer_data_question(question: str, sink: llm.Sink, *, con=None) -> DataResult:
    owns_con = con is None
    con = con if con is not None else db.connect()
    try:
        def _get_schema() -> str:
            return schema.schema_context(con)

        def _run_sql(sql: str) -> str:
            return json.dumps(db.run_sql(con, sql))

        result = llm.run_agent(
            model=DATA_AGENT_MODEL,
            system=_SYSTEM.format(schema=schema.schema_context(con)),
            messages=[{"role": "user", "content": question}],
            tools=_TOOLS,
            tool_impls={"get_schema": _get_schema, "run_sql": _run_sql},
            sink=sink,
            step_label=_step_label,
        )
    finally:
        if owns_con:
            con.close()

    last = next(
        (tc for tc in reversed(result.tool_calls) if tc.name == "run_sql" and not tc.is_error),
        None,
    )
    if last is None:
        return DataResult(ok=False, error="data agent produced no successful query", notes=result.final_text)

    payload = json.loads(last.result)
    return DataResult(
        ok=True,
        sql=payload["sql"],
        columns=payload["columns"],
        rows=payload["rows"],
        row_count=payload["row_count"],
        truncated=payload["truncated"],
        notes=result.final_text,
    )
