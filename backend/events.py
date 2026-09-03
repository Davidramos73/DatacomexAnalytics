from __future__ import annotations

import dataclasses
import json
from typing import Union


@dataclasses.dataclass(frozen=True)
class Step:
    label: str
    detail: str = ""
    type: str = dataclasses.field(default="step", init=False)


@dataclasses.dataclass(frozen=True)
class Thinking:
    label: str
    type: str = dataclasses.field(default="thinking", init=False)


@dataclasses.dataclass(frozen=True)
class Text:
    text: str
    type: str = dataclasses.field(default="text", init=False)


@dataclasses.dataclass(frozen=True)
class Chart:
    title: str
    meta: str
    spec: dict
    data: dict
    type: str = dataclasses.field(default="chart", init=False)


@dataclasses.dataclass(frozen=True)
class ErrorEvent:
    message: str
    type: str = dataclasses.field(default="error", init=False)


@dataclasses.dataclass(frozen=True)
class Done:
    seconds: float
    type: str = dataclasses.field(default="done", init=False)


Event = Union[Step, Thinking, Text, Chart, ErrorEvent, Done]


def to_sse(event: Event) -> str:
    payload = {
        f.name: getattr(event, f.name)
        for f in dataclasses.fields(event)
        if f.name != "type"
    }
    return f"event: {event.type}\ndata: {json.dumps(payload)}\n\n"
