from __future__ import annotations

import dataclasses
from typing import Any, Callable, Literal

ParamType = Literal["enum", "int", "str", "period"]


@dataclasses.dataclass(frozen=True)
class Param:
    name: str
    type: ParamType
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    ui_label: str | None = None
    ui_options: list[dict] | None = None
    ui_options_from: str | None = None
    ui_option_label: str | None = None


@dataclasses.dataclass(frozen=True)
class Widget:
    key: str
    fn: Callable[..., dict]
    params: list[Param]
    rest_path: str
    tool_name: str
    tool_description: str
    chart_types: list[str] | None = None
    span: Literal["full", "half"] = "full"
    in_grid: bool = True


def chart_type_param(chart_types: list[str]) -> Param:
    return Param(
        name="chart_type",
        type="enum",
        required=False,
        default=chart_types[0],
        enum=list(chart_types),
        ui_label=None,
    )
