from __future__ import annotations

import dataclasses
import json

from backend import events
from backend.agents import llm
from backend.config import DATA_AGENT_MODEL
from backend.warehouse import db, schema

_SYSTEM = """\
You are a senior data analyst with read-only access to a small analytics warehouse.
The full schema, business notes and sample rows are below - you do NOT need to look
them up.

{schema}

Do exactly this:
1. Call run_sql ONCE with a single SQL SELECT that answers the question. Prefer one
   GROUP BY aggregation; alias columns in friendly snake_case; keep the result to a
   handful of rows (ideal for charting).
2. Then state in one sentence what the data shows. Do not call run_sql again unless
   it returned an error - if so, fix the SQL and retry once.
"""

_TOOLS = [
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
    return events.Step(label=name)


def answer_data_question(question: str, sink: llm.Sink, *, con=None) -> DataResult:
    owns_con = con is None
    con = con if con is not None else db.connect()
    try:
        schema_ctx = schema.schema_context(con)

        def _run_sql(sql: str) -> str:
            return json.dumps(db.run_sql(con, sql))

        result = llm.run_agent(
            model=DATA_AGENT_MODEL,
            system=_SYSTEM.format(schema=schema_ctx),
            messages=[{"role": "user", "content": question}],
            tools=_TOOLS,
            tool_impls={"run_sql": _run_sql},
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
