"""Footwear chat tools — generated from WIDGETS, plus resolve_footwear_product."""
from __future__ import annotations

import json

from backend.services import footwear
from backend.services.footwear_widgets import WIDGETS
from backend.widgets import build_tool_set

REPORT_TOOLS = {w.tool_name for w in WIDGETS}

_RESOLVE_DEF = {
    "name": "resolve_footwear_product",
    "description": (
        "Traduce un tipo de calzado en lenguaje natural (p. ej. 'deportivas', "
        "'botas de agua', 'de cuero') a su partida TARIC de 4 dígitos. "
        "LLÁMALO SIEMPRE primero si el usuario usa términos coloquiales de producto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"term": {"type": "string"}},
        "required": ["term"],
        "additionalProperties": False,
    },
}


def tool_defs() -> list[dict]:
    return [_RESOLVE_DEF] + build_tool_set(WIDGETS, con=None)["defs"]


def handlers(con) -> dict:
    h = build_tool_set(WIDGETS, con)["handlers"]
    h["resolve_footwear_product"] = lambda term: json.dumps(
        {"heading": footwear.resolve_taric(con, term)}
    )
    return h
