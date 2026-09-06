"""Footwear report endpoints — generated from the WIDGETS descriptor list."""
from __future__ import annotations

import duckdb

import backend.config as config
from backend.services.footwear import filter_options
from backend.services.footwear_widgets import REST_PREFIX, WIDGETS
from backend.widgets import build_rest_router


def _con():
    return duckdb.connect(str(config.DATACOMEX_PATH), read_only=True)


router = build_rest_router(WIDGETS, prefix=REST_PREFIX, con_factory=_con)


@router.get("/filters/options")
def _filters():
    con = _con()
    try:
        return filter_options(con)
    finally:
        con.close()
