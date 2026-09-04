"""Deterministic synthetic DataComex warehouse (footwear, TARIC chapter 64).

Stand-in for the real ingest pipeline. Same schema, plausible magnitudes and
seasonality — enough to build and test `services/footwear.py` and to demo the
reports page before real data lands.

    python -m backend.warehouse.datacomex_seed
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from pathlib import Path

import duckdb

import backend.config as config
from backend.config import RANDOM_SEED
from backend.warehouse.datacomex_schema import (
    HEADINGS,
    SCHEMA_DDL,
    SUBHEADINGS,
)

# NB: the file stem must differ from the schema name ("datacomex"), otherwise
# DuckDB can't tell `datacomex.table` (catalog) from `datacomex.table` (schema).
# Kept as an alias for backward compatibility; config.DATACOMEX_PATH is the
# source of truth (env-overridable, shared with build_warehouse.py).
DATACOMEX_PATH = config.DATACOMEX_PATH

_MONTHS = 36
_END = (2025, 12)  # last (year, month); provisional

# (iso_a3, name, import_pull, export_pull) — Spain's real footwear partners
_COUNTRIES = [
    ("CHN", "China", 3.4, 0.4),
    ("VNM", "Vietnam", 2.1, 0.3),
    ("ITA", "Italia", 0.7, 1.8),
    ("PRT", "Portugal", 0.5, 1.3),
    ("FRA", "Francia", 0.4, 2.0),
    ("DEU", "Alemania", 0.4, 1.4),
    ("MAR", "Marruecos", 0.6, 0.6),
    ("IND", "India", 0.6, 0.3),
]

# €/kg reference price per heading (leather dearest, textile cheapest)
_PRICE_PER_KG = {
    "6401": 9.0, "6402": 11.0, "6403": 34.0,
    "6404": 13.0, "6405": 16.0, "6406": 18.0,
}
_HEADING_BASE = {  # relative monthly value weight
    "6401": 0.7, "6402": 1.6, "6403": 2.4,
    "6404": 2.0, "6405": 0.5, "6406": 0.8,
}
_KG_PER_PAIR = 0.45


def _periods() -> list[tuple[str, int, int]]:
    y, m = _END
    out = []
    for _ in range(_MONTHS):
        out.append((f"{y:04d}-{m:02d}", y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(out)


def _rows() -> list[tuple]:
    rng = random.Random(RANDOM_SEED)
    periods = _periods()
    max_period = periods[-1][0]
    rows: list[tuple] = []

    for idx, (period, year, month) in enumerate(periods):
        seasonal = 1.0 + 0.18 * math.sin(2 * math.pi * (month - 3) / 12)
        trend = 1.0 + 0.006 * idx
        for flow, pull_ix in (("IMPORT", 2), ("EXPORT", 3)):
            for heading, codes in SUBHEADINGS.items():
                has_pairs = HEADINGS[heading][1]
                for code in codes:
                    for iso, name, *pull in _COUNTRIES:
                        base = pull[pull_ix - 2] * _HEADING_BASE[heading]
                        if base < 0.25:  # sparse tail
                            continue
                        noise = rng.uniform(0.8, 1.2)
                        value = int(base * seasonal * trend * noise * 42_000 / len(codes))
                        if value <= 0:
                            continue
                        weight = int(value / _PRICE_PER_KG[heading] / rng.uniform(0.9, 1.1))
                        units = int(weight / _KG_PER_PAIR) if has_pairs else None
                        rows.append((
                            flow, period, year, month, iso, name, code,
                            "64", heading, value, max(weight, 1), units,
                            period == max_period,
                        ))
    return rows


def _tree_rows() -> list[tuple]:
    rows = [("64", None, 2, "Calzado, polainas y artículos análogos; sus partes")]
    for heading, (desc, _) in HEADINGS.items():
        rows.append((heading, "64", 4, desc))
        for code in SUBHEADINGS[heading]:
            rows.append((code, heading, 6, f"{desc} — subpartida {code}"))
    return rows


def build(path: Path | None = None) -> None:
    path = Path(path) if path is not None else DATACOMEX_PATH
    if path.exists():
        path.unlink()

    con = duckdb.connect(str(path))
    try:
        con.execute(SCHEMA_DDL)

        tree = _tree_rows()
        rows = _rows()

        con.execute("BEGIN")
        con.executemany(
            "INSERT INTO datacomex.taric_tree VALUES (?, ?, ?, ?)", tree
        )
        # DataFrame-free bulk load: register the list of tuples as a relation.
        cols = (
            "flow, period, year, month, country_code, country_name, taric_code, "
            "chapter, heading, value_eur, weight_kg, suppl_units, is_provisional"
        )
        con.executemany(
            f"INSERT INTO datacomex.trade_flows ({cols}) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        con.execute(
            "INSERT INTO datacomex.meta_ingestion VALUES (?, ?, ?, ?, ?)",
            [1, datetime.now(timezone.utc), _periods()[-1][0], len(rows), "synthetic"],
        )
        con.execute("COMMIT")
    finally:
        con.close()


if __name__ == "__main__":
    build()
    print(f"DataComex warehouse built at {DATACOMEX_PATH}")
