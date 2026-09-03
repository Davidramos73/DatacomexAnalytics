from __future__ import annotations

import duckdb

SCHEMA_NOTES = """\
Business notes (read carefully before writing SQL):

- fct_orders: one row per order line. Grain = order.
  - net_revenue: revenue in USD (not thousands, not millions).
  - discount_pct, gross_margin_pct: percentages on a 0-100 scale.
  - quarter: string like '2026Q3'. week: string like 'W7' (W1..W13 within a quarter).
  - Use this table for revenue trends, breakdowns by region/channel/segment.
- dim_region: lookup, region -> macro_area.
- mart_account_health: pre-aggregated, one row per (segment, avg_discount bucket).
  - gross_margin: percentage 0-100. accounts: count of accounts in the bucket.
  - Use this table for discount-vs-margin questions.

Rules: SELECT only. Prefer GROUP BY aggregations over raw rows. Give output
columns friendly snake_case aliases. Divide revenue by 1e6 when the user asks
for "millions".
"""


def introspect(con: duckdb.DuckDBPyConnection) -> str:
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()]
    lines = []
    for table in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        col_str = ", ".join(f"{name} {dtype}" for name, dtype in cols)
        lines.append(f"{table}({col_str})")
    return "\n".join(lines)


def _sample_rows(con: duckdb.DuckDBPyConnection, table: str, n: int = 3) -> str:
    rel = con.execute(f"SELECT * FROM {table} LIMIT {n}")
    cols = [d[0] for d in rel.description]
    rows = rel.fetchall()
    header = " | ".join(cols)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
    return f"{table}:\n{header}\n{body}"


def schema_context(con: duckdb.DuckDBPyConnection) -> str:
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()]
    samples = "\n\n".join(_sample_rows(con, t) for t in tables)
    return (
        "TABLES:\n"
        + introspect(con)
        + "\n\n"
        + SCHEMA_NOTES
        + "\nSAMPLE ROWS:\n"
        + samples
    )
