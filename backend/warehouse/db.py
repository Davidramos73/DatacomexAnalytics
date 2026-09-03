from __future__ import annotations

import re
from pathlib import Path

import duckdb

from backend.config import SQL_MAX_ROWS, SQL_TIMEOUT_S, WAREHOUSE_PATH

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|COPY|PRAGMA|"
    r"INSTALL|LOAD|SET|CALL|EXPORT|IMPORT)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


class UnsafeSQLError(ValueError):
    """Raised when a SQL string is not a safe read-only single SELECT."""


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(path) if path is not None else WAREHOUSE_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Warehouse not found at {path}. Run: python -m backend.warehouse.seed"
        )
    return duckdb.connect(str(path), read_only=True)


def _sanitize(sql: str) -> str:
    stripped = _COMMENT.sub(" ", sql).strip().rstrip(";").strip()
    if not stripped:
        raise UnsafeSQLError("Empty query.")
    if ";" in stripped:
        raise UnsafeSQLError("Multiple statements are not allowed.")
    lowered = stripped.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise UnsafeSQLError("Only SELECT / WITH queries are allowed.")
    if _FORBIDDEN.search(stripped):
        raise UnsafeSQLError("Query contains a forbidden keyword.")
    return stripped


def _has_outer_limit(sql: str) -> bool:
    # crude but effective: a top-level LIMIT near the end
    return re.search(r"\blimit\b\s+\d+\s*$", sql, re.IGNORECASE) is not None


def run_sql(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    max_rows: int | None = None,
    timeout_s: float | None = None,
) -> dict:
    max_rows = SQL_MAX_ROWS if max_rows is None else max_rows
    timeout_s = SQL_TIMEOUT_S if timeout_s is None else timeout_s
    clean = _sanitize(sql)

    if _has_outer_limit(clean):
        effective = clean
        cap = max_rows
    else:
        effective = f"SELECT * FROM (\n{clean}\n) AS _q LIMIT {max_rows + 1}"
        cap = max_rows

    try:
        con.execute(f"SET statement_timeout = '{int(timeout_s * 1000)}ms'")
    except duckdb.Error:
        pass  # older DuckDB: no statement_timeout; rely on data size

    rel = con.execute(effective)
    columns = [d[0] for d in rel.description]
    rows = [list(r) for r in rel.fetchall()]
    truncated = len(rows) > cap
    if truncated:
        rows = rows[:cap]
    return {
        "sql": clean,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }
