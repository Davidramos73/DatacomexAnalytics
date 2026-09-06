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


def _param_dict(p: Param) -> dict:
    return {
        "name": p.name, "type": p.type, "required": p.required,
        "default": p.default, "enum": p.enum, "ui_label": p.ui_label,
        "ui_options": p.ui_options, "ui_options_from": p.ui_options_from,
        "ui_option_label": p.ui_option_label,
    }


def widget_descriptors(widgets: list[Widget]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for w in widgets:
        out[w.key] = {
            "rest_path": w.rest_path,
            "span": w.span,
            "params": [
                _param_dict(p) for p in w.params if p.name != "chart_type"
            ],
        }
    return out
