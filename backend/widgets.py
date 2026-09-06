from __future__ import annotations

import contextlib
import dataclasses
import inspect
import json
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

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


_PY_TYPE = {"enum": str, "str": str, "period": str, "int": int}


def _dependency(con_factory):
    def _dep():
        con = con_factory()
        try:
            yield con
        finally:
            close = getattr(con, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()

    return _dep


def _query_parser(w: Widget):
    params = [p for p in w.params if p.name != "chart_type"]

    def parse(**kwargs):
        out = {}
        for p in params:
            val = kwargs.get(p.name)
            if val is None:
                if p.required:
                    raise HTTPException(422, f"missing required param {p.name}")
                continue
            if p.type == "enum" and p.enum and val not in p.enum:
                raise HTTPException(422, f"{p.name} must be one of {p.enum}")
            out[p.name] = val
        return out

    sig_params = []
    for p in params:
        py = _PY_TYPE[p.type]
        if p.required:
            default = Query(...)
            annotation = py
        else:
            default = Query(p.default)
            annotation = Optional[py]
        sig_params.append(
            inspect.Parameter(
                p.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )
    parse.__signature__ = inspect.Signature(sig_params)
    return parse


def _make_endpoint(w: Widget, dep):
    parser = _query_parser(w)

    def endpoint(request_params: dict = Depends(parser), con=Depends(dep)):
        return w.fn(con, **request_params)

    return endpoint


def build_rest_router(
    widgets: list[Widget], *, prefix: str, con_factory: Callable[[], Any]
) -> APIRouter:
    router = APIRouter(prefix=prefix)
    dep = _dependency(con_factory)
    for w in widgets:
        router.add_api_route(
            w.rest_path,
            _make_endpoint(w, dep),
            methods=["GET"],
            name=w.key,
        )
    return router


_JSON_TYPE = {"enum": "string", "str": "string", "period": "string", "int": "integer"}


def _tool_def(w: Widget) -> dict:
    props: dict = {}
    required: list[str] = []
    for p in w.params:
        schema = {"type": _JSON_TYPE[p.type]}
        if p.enum:
            schema["enum"] = list(p.enum)
        if p.ui_label:
            schema["description"] = p.ui_label
        props[p.name] = schema
        if p.required:
            required.append(p.name)
    return {
        "name": w.tool_name,
        "description": w.tool_description,
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
    }


def _handler(w: Widget, con):
    int_params = {p.name for p in w.params if p.type == "int"}

    def run(**kw):
        coerced = {k: (int(v) if k in int_params and v is not None else v)
                   for k, v in kw.items()}
        return json.dumps(w.fn(con, **coerced))

    return run


def build_tool_set(widgets: list[Widget], con) -> dict:
    return {
        "defs": [_tool_def(w) for w in widgets],
        "handlers": {w.tool_name: _handler(w, con) for w in widgets},
    }
