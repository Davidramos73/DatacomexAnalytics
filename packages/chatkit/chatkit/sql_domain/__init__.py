"""SqlDomain — the free-SQL chat mode as a Domain object.

Ported from backend/agents/orchestrator.py (deleted in a later task).
"""
from __future__ import annotations

import json
from pathlib import Path

import chatkit.config as config
from chatkit import charts
from chatkit.agents import llm
from chatkit.sql_domain.data_agent import answer_data_question
from chatkit.domain import AppConfig, Branding
from chatkit.config import LLM_MODEL
from chatkit.warehouse import duckdb as db

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

_CLOSEOUT = (
    "Explain what this result shows in 1-3 short sentences of plain prose. "
    "No JSON, no markdown, no chart."
)

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

_CHART_SCHEMA = {
    "type": "object",
    "properties": {
        "chart_title": {"type": "string", "description": "a short plain-text title"},
        "chart_meta": {
            "type": "string",
            "description": "one short plain-text line about the chart (a string, not an object)",
        },
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
        "chart_title", "chart_meta",
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


class SqlDomain:
    settings = config
    system_prompt = _SYSTEM
    prose_closeout_instruction = _CLOSEOUT

    def __init__(self) -> None:
        self._datasets: list = []

    def app_config(self) -> AppConfig:
        return AppConfig(
            branding=Branding(
                name="Analytics",
                short_name="Analytics",
                badge="SQL",
                favicon="📊",
            ),
            example_prompts=[],
            echarts_themes=["lumen", "default"],
            tabs=[],
        )

    def open_connection(self):
        return db.connect()

    def widgets(self):
        return []

    def report_prefix(self):
        return None

    def filter_options(self, con) -> dict:
        return {}

    def web_dir(self) -> str:
        return str(Path(__file__).parent.parent / "_demo" / "web")

    def step_label(self, name: str, tool_input: dict):
        return None

    def extra_tools(self, con) -> dict:
        def query_data(question: str) -> str:
            result = answer_data_question(question, sink=lambda e: None)
            self._datasets.append(result)
            if not result.ok:
                return json.dumps({"error": result.error})
            payload = {
                "sql": result.sql,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
            }
            ok_so_far = sum(1 for d in self._datasets if d.ok)
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

        return {
            "defs": [_QUERY_DATA_TOOL],
            "handlers": {"query_data": query_data},
        }

    def _chart_mapping(self, agent) -> dict:
        dataset = self._pick_dataset()
        result_ctx = (
            f"\nResult columns: {dataset.columns}\n"
            + json.dumps({"rows": dataset.rows[:50]})
        )
        messages = (agent.messages if agent is not None else []) + [
            {
                "role": "user",
                "content": "Choose the chart for this result. chart_x, chart_y and "
                "chart_series_by must be exact column names from it; ignore columns "
                "from any earlier query." + result_ctx,
            }
        ]
        return llm.structured_json(
            model=LLM_MODEL,
            system=_SYSTEM,
            messages=messages,
            tools=[_QUERY_DATA_TOOL],
            schema=_CHART_SCHEMA,
            schema_name="chart_mapping",
        )

    def _pick_dataset(self):
        ok_datasets = [d for d in self._datasets if d.ok]
        if not ok_datasets:
            return None
        return max(
            enumerate(ok_datasets),
            key=lambda t: (_chartability(t[1]), t[0]),
        )[1]

    def finalize(self, agent, con) -> dict | None:
        dataset = self._pick_dataset()
        if dataset is None:
            return None

        mapping = self._chart_mapping(agent)

        for key in ("chart_title", "chart_meta"):
            val = mapping.get(key)
            if not val:
                mapping[key] = ""
            elif isinstance(val, str):
                mapping[key] = val
            elif isinstance(val, dict):
                mapping[key] = ", ".join(str(v) for v in val.values())
            else:
                mapping[key] = str(val)

        chart = {
            "chart_type": mapping.get("chart_type"),
            "x": mapping.get("chart_x"),
            "y": mapping.get("chart_y"),
            "series_by": mapping.get("chart_series_by"),
        }

        try:
            spec = charts.build_option(chart, dataset.columns, dataset.rows)
        except charts.ChartError:
            return None

        return {
            "widget": None,
            "title": mapping["chart_title"],
            "echarts": spec,
            "kpis": [],
            "meta": {"notes": [mapping["chart_meta"]] if mapping["chart_meta"] else []},
            "data": {"columns": dataset.columns, "rows": dataset.rows},
        }
