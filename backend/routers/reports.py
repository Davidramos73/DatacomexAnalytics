"""Canned footwear report endpoints.

Each returns the same envelope `{widget, title, echarts, kpis, meta}` — the
report page is a generic grid that renders `echarts` and `kpis` by config.
Thin wrappers over `backend.services.footwear`; no domain SQL here.
"""
from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends

from backend.services import footwear
from backend.warehouse.datacomex_seed import DATACOMEX_PATH

router = APIRouter(prefix="/api/v1/reports/footwear", tags=["footwear"])


def get_footwear_con():
    con = duckdb.connect(str(DATACOMEX_PATH), read_only=True)
    try:
        yield con
    finally:
        con.close()


@router.get("/filters/options")
def filter_options(con=Depends(get_footwear_con)) -> dict:
    return footwear.filter_options(con)


@router.get("/evolution")
def evolution(
    flow: str,
    taric: str = "64",
    months: int = 24,
    con=Depends(get_footwear_con),
) -> dict:
    return footwear.evolution(
        con, flow=flow.upper(), heading=taric, months=months
    )


@router.get("/countries")
def countries(
    flow: str,
    taric: str = "64",
    period_from: str | None = None,
    period_to: str | None = None,
    top_n: int = 10,
    con=Depends(get_footwear_con),
) -> dict:
    return footwear.country_ranking(
        con,
        flow=flow.upper(),
        heading=taric,
        period_from=period_from,
        period_to=period_to,
        top_n=top_n,
    )
