from __future__ import annotations

import dataclasses
import json
from typing import Any, Literal, Protocol

from chatkit import events
from chatkit.widgets import Widget


@dataclasses.dataclass(frozen=True)
class Branding:
    name: str
    short_name: str
    badge: str
    favicon: str


@dataclasses.dataclass(frozen=True)
class TabDescriptor:
    id: str
    label: str
    icon: str
    kind: Literal["widget_grid", "custom"]
    widgets: list[str] | None = None
    filters: list[str] | None = None


@dataclasses.dataclass(frozen=True)
class AppConfig:
    branding: Branding
    example_prompts: list[str]
    echarts_themes: list[str]
    tabs: list[TabDescriptor]
    # UI copy overrides consumed by chatkit.js: empty_title, empty_text,
    # placeholder, hint_html. Any missing key falls back to a generic default.
    copy: dict = dataclasses.field(default_factory=dict)


class Domain(Protocol):
    settings: Any
    system_prompt: str
    prose_closeout_instruction: str

    def app_config(self) -> AppConfig: ...
    def open_connection(self) -> Any: ...
    def widgets(self) -> list[Widget]: ...
    def extra_tools(self) -> dict | None: ...
    def web_dir(self) -> str: ...
    def finalize(self, agent, con) -> dict | None: ...
    def step_label(self, name: str, tool_input: dict) -> events.Step | None: ...
    def report_prefix(self) -> str | None: ...
    def filter_options(self, con) -> dict: ...


def default_step_label(name: str, tool_input: dict) -> events.Step:
    detail = " · ".join(
        f"{k}={v}" for k, v in tool_input.items() if v is not None
    )
    return events.Step(label=name, detail=detail)


def default_finalize(agent, con, *, report_tool_names: set[str]) -> dict | None:
    for tc in reversed(agent.tool_calls):
        if tc.name in report_tool_names and not tc.is_error:
            try:
                return json.loads(tc.result)
            except (json.JSONDecodeError, TypeError):
                return None
    return None
