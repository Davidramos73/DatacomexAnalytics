"""Build datacomex.duckdb from the real DataComex API.

Offline job (spec §8.1): the app only ever reads this file read-only; this
script replaces it. Pulls newest periods first so an interrupted run still
leaves the most useful data in place.

    python -m projects.footwear.ingest.build_warehouse [--from-year 2015]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from projects.footwear.ingest import transform
from projects.footwear.ingest.client import DataComexClient
from projects.footwear.warehouse.schema import COMPONENT_PARTIDAS, HEADINGS, SCHEMA_DDL

_TARIC_PARAM = ".".join(f"H{h}" for h in HEADINGS)
# ObtenerDatos accepts one `ta` per call — components span unrelated chapters
# (39, 40, 41...) so, unlike footwear headings, they can't be joined into a
# single "H..." param and must be pulled one partida at a time.


def _select_periods(raw_periods: list[dict], from_year: int) -> list[str]:
    months = [
        p["CodPeriodo"]
        for p in raw_periods
        if p.get("Nivel") == "2" and int(p["CodPeriodo"][:4]) >= from_year
    ]
    return sorted(set(months), reverse=True)  # newest first


def _tree_rows(raw_tree: list[dict]) -> list[tuple]:
    """ObtenerTarics returns the *entire* nomenclature (all ~99 chapters);
    keep only numeric, chapter-64 (footwear) codes."""
    rows = []
    for t in raw_tree:
        code = t["Taric"]
        if not code.isdigit() or not code.startswith("64"):
            continue  # other chapters, or special codes: 64CC/64MM/64PP/64SS...
        parent = t.get("TaricPadre") or None
        rows.append((code, parent, len(code), t.get("Nombre", code)))
    return rows


def build(
    *,
    path: str | Path,
    client: DataComexClient,
    from_year: int = 2015,
    flow: str = "I/E",
    with_components: bool = True,
) -> None:
    path = Path(path)
    if path.exists():
        path.unlink()

    periods = _select_periods(client.get_periods(), from_year)
    tree_rows = _tree_rows(client.get_taric_tree())

    total_rows = 0
    con = duckdb.connect(str(path))
    try:
        con.execute(SCHEMA_DDL)
        con.execute("BEGIN")
        con.executemany(
            "INSERT INTO datacomex.taric_tree VALUES (?, ?, ?, ?)", tree_rows
        )
        for cod_periodo in periods:
            label, year, month = transform.period_label(cod_periodo)
            api_rows = client.get_data(
                flow=flow, period=cod_periodo, taric=_TARIC_PARAM
            )
            rows = [
                transform.row_to_tuple(
                    r,
                    flow=transform.flow_of(r.get("flujo")),
                    period=label,
                    year=year,
                    month=month,
                )
                for r in api_rows
            ]
            if rows:
                con.executemany(
                    "INSERT INTO datacomex.trade_flows "
                    "(flow, period, year, month, country_code, country_name, "
                    "taric_code, chapter, heading, value_eur, weight_kg, "
                    "suppl_units, is_provisional) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows,
                )
                total_rows += len(rows)

        if with_components:
            total_rows += _ingest_components(con, client, periods)

        con.execute(
            "INSERT INTO datacomex.meta_ingestion VALUES (?, ?, ?, ?, ?)",
            [
                1,
                datetime.now(timezone.utc),
                periods[0] if periods else "",
                total_rows,
                "api",
            ],
        )
        con.execute("COMMIT")
    finally:
        con.close()


def _ingest_components(
    con: duckdb.DuckDBPyConnection, client: DataComexClient, periods: list[str]
) -> int:
    """Bloque A: pull each of the 70 component partidas, one `ta` per call
    (they span unrelated chapters, so they can't share a request like the
    footwear headings do). Same periods/flow window as calzado terminado."""
    total_rows = 0
    for cod_periodo in periods:
        label, year, month = transform.period_label(cod_periodo)
        for partida in COMPONENT_PARTIDAS:
            api_rows = client.get_data(flow="I/E", period=cod_periodo, taric=partida)
            rows = [
                transform.component_row_to_tuple(
                    r,
                    partida=partida,
                    flow=transform.flow_of(r.get("flujo")),
                    period=label,
                    year=year,
                    month=month,
                )
                for r in api_rows
            ]
            if rows:
                con.executemany(
                    "INSERT INTO datacomex.component_flows "
                    "(flow, period, year, month, country_code, country_name, "
                    "partida, value_eur, weight_kg, is_provisional) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    rows,
                )
                total_rows += len(rows)
    return total_rows


def main() -> None:
    import chatkit.config as config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2015)
    parser.add_argument("--path", default=None)
    parser.add_argument(
        "--no-components", action="store_true",
        help="Skip Bloque A (adds ~70x the API calls per period)",
    )
    args = parser.parse_args()

    if not config.DATA_COMEX_TOKEN:
        raise SystemExit("DATA_COMEX_TOKEN is not set")
    client = DataComexClient(token=config.DATA_COMEX_TOKEN)
    target = Path(args.path) if args.path else config.DATACOMEX_PATH
    build(
        path=target, client=client, from_year=args.from_year,
        with_components=not args.no_components,
    )
    print(f"Warehouse built at {target}")


if __name__ == "__main__":
    main()
