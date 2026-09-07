"""Map a raw DataComex ObtenerDatos row to a datacomex.trade_flows row.

Pure functions, no network — kept separate from the HTTP client so they're
trivial to unit test.
"""
from __future__ import annotations


def parse_number(value: str | None) -> float:
    """DataComex numbers use a comma decimal separator, no thousands sep."""
    if not value:
        return 0.0
    return float(str(value).replace(",", "."))


def heading_of(taric_code: str) -> str:
    return taric_code[:4]


def is_provisional(mensaje: str | None) -> bool:
    return bool(mensaje) and "provisional" in mensaje.lower()


def flow_of(text: str) -> str:
    return "IMPORT" if "mport" in (text or "") else "EXPORT"


def period_label(cod_periodo: str) -> tuple[str, int, int]:
    """DataComex month code 'YYYYMM' -> (our 'YYYY-MM' label, year, month)."""
    year, month = int(cod_periodo[:4]), int(cod_periodo[4:6])
    return f"{year:04d}-{month:02d}", year, month


def row_to_tuple(
    api_row: dict, *, flow: str, period: str, year: int, month: int
) -> tuple:
    """(flow, period, year, month, country_code, country_name, taric_code,
    chapter, heading, value_eur, weight_kg, suppl_units, is_provisional)

    suppl_units is always None: ObtenerDatos doesn't return unit counts.
    """
    taric = api_row["taric"]
    return (
        flow,
        period,
        year,
        month,
        api_row["id_pais"],
        api_row["pais"],
        taric,
        "64",
        heading_of(taric),
        parse_number(api_row.get("euros")),
        parse_number(api_row.get("kilos")),
        None,
        is_provisional(api_row.get("mensaje")),
    )
