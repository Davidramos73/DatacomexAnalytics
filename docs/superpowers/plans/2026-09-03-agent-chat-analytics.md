# Agent Chat Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend multi-agente (orquestador + agente de datos) que responde consultas en lenguaje natural ejecutando SQL read-only contra DuckDB y devuelve una spec Vega-Lite que una UI mínima renderiza inline, con streaming SSE del tool-trace.

**Architecture:** FastAPI expone `POST /api/chat` como `text/event-stream`. El orquestador (Claude, loop de tool-use manual) delega en el agente de datos vía la tool `query_data`; el agente de datos conoce el schema y ejecuta SQL con `get_schema`/`run_sql`. El orquestador cierra con una llamada `output_config.format` que garantiza `{answer, chart_title, chart_meta, vega_lite_spec}`. Los eventos SSE (`step`, `thinking`, `text`, `chart`, `error`, `done`) mapean 1:1 con el modelo de mensajes del mockup.

**Tech Stack:** Python 3.11+, `anthropic` SDK (loop de tool-use manual, no el tool_runner beta), FastAPI + uvicorn, DuckDB (read-only), pytest + httpx TestClient. Frontend: `index.html` vanilla JS con vega/vega-lite/vega-embed por CDN.

**Spec:** `docs/superpowers/specs/2026-09-03-agent-chat-analytics-design.md`

## Global Constraints

- Modelo por defecto `claude-opus-5`; overridable por env `LLM_MODEL`. Agente de datos: env `DATA_AGENT_MODEL` (default = `LLM_MODEL`).
- Thinking adaptativo en toda llamada a Claude: `thinking={"type": "adaptive"}`.
- `max_tokens=16000` en las llamadas a Claude.
- Loop agéntico **manual** (`while stop_reason == "tool_use"`). No usar `client.beta.messages.tool_runner`.
- Cliente Anthropic: `anthropic.Anthropic()` sin argumentos (credenciales del entorno). Nunca hardcodear la key.
- Base de datos siempre `read_only=True`. Ningún componente escribe a la warehouse en runtime (solo `seed.py` la construye).
- `SQL_MAX_ROWS=500`, `MAX_AGENT_ITERS=6`, `SQL_TIMEOUT_S=10` — constantes en `backend/config.py`, overridables por env.
- Todo el código Python nuevo va bajo el paquete `backend/` con `__init__.py` en cada subdirectorio. Tests bajo `tests/`.
- Imports absolutos desde `backend` (`from backend.warehouse import db`). Ejecutar pytest desde la raíz del repo.
- Datos sintéticos deterministas: `random.Random(42)`.

---

### Task 1: Scaffolding, configuración y dependencias

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `backend/__init__.py` (vacío)
- Create: `backend/agents/__init__.py` (vacío)
- Create: `backend/warehouse/__init__.py` (vacío)
- Create: `tests/__init__.py` (vacío)
- Create: `backend/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada.
- Produces: `backend.config` con:
  - `LLM_MODEL: str`, `DATA_AGENT_MODEL: str`
  - `MAX_AGENT_ITERS: int`, `SQL_MAX_ROWS: int`, `SQL_TIMEOUT_S: float`
  - `WAREHOUSE_PATH: pathlib.Path`
  - `MAX_TOKENS: int = 16000`
  - `RANDOM_SEED: int = 42`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import importlib


def test_defaults(monkeypatch):
    for var in ("LLM_MODEL", "DATA_AGENT_MODEL", "MAX_AGENT_ITERS", "SQL_MAX_ROWS"):
        monkeypatch.delenv(var, raising=False)
    import backend.config as config
    importlib.reload(config)
    assert config.LLM_MODEL == "claude-opus-5"
    assert config.DATA_AGENT_MODEL == "claude-opus-5"
    assert config.MAX_AGENT_ITERS == 6
    assert config.SQL_MAX_ROWS == 500
    assert config.MAX_TOKENS == 16000
    assert config.WAREHOUSE_PATH.name == "warehouse.duckdb"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("MAX_AGENT_ITERS", "3")
    import backend.config as config
    importlib.reload(config)
    assert config.LLM_MODEL == "claude-sonnet-5"
    assert config.DATA_AGENT_MODEL == "claude-sonnet-5"  # falls back to LLM_MODEL
    assert config.MAX_AGENT_ITERS == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.config'`

- [ ] **Step 3: Create scaffolding files**

`requirements.txt`:
```
anthropic>=0.116
fastapi>=0.110
uvicorn[standard]>=0.27
duckdb>=0.10
pytest>=8.0
httpx>=0.27
```

`.env.example`:
```
ANTHROPIC_API_KEY=
# Optional overrides:
# LLM_MODEL=claude-opus-5
# DATA_AGENT_MODEL=claude-sonnet-5
```

`.gitignore`:
```
__pycache__/
*.pyc
.env
.venv/
venv/
backend/warehouse/warehouse.duckdb
.pytest_cache/
```

Create the empty `__init__.py` files listed above.

- [ ] **Step 4: Write `backend/config.py`**

```python
import os
from pathlib import Path

LLM_MODEL = os.environ.get("LLM_MODEL", "claude-opus-5")
DATA_AGENT_MODEL = os.environ.get("DATA_AGENT_MODEL", LLM_MODEL)

MAX_AGENT_ITERS = int(os.environ.get("MAX_AGENT_ITERS", "6"))
SQL_MAX_ROWS = int(os.environ.get("SQL_MAX_ROWS", "500"))
SQL_TIMEOUT_S = float(os.environ.get("SQL_TIMEOUT_S", "10"))
MAX_TOKENS = 16000
RANDOM_SEED = 42

WAREHOUSE_PATH = Path(
    os.environ.get(
        "WAREHOUSE_PATH",
        str(Path(__file__).parent / "warehouse" / "warehouse.duckdb"),
    )
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore backend tests
git commit -m "feat: project scaffolding and config"
```

---

### Task 2: Warehouse seed

**Files:**
- Create: `backend/warehouse/seed.py`
- Test: `tests/test_warehouse_seed.py`

**Interfaces:**
- Consumes: `backend.config.WAREHOUSE_PATH`, `backend.config.RANDOM_SEED`.
- Produces:
  - `build(path: pathlib.Path | None = None) -> None` — (re)crea el archivo DuckDB con las tablas `dim_region`, `fct_orders`, `mart_account_health`. Borra el archivo previo si existe.
  - `TABLES: list[str]` = `["dim_region", "fct_orders", "mart_account_health"]`
  - Ejecutable: `python -m backend.warehouse.seed` llama a `build()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_warehouse_seed.py
import duckdb
from backend.warehouse import seed


def test_build_creates_tables(tmp_path):
    db_path = tmp_path / "w.duckdb"
    seed.build(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for table in seed.TABLES:
            (count,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert count > 0, f"{table} is empty"
        # fct_orders has the columns the agents rely on
        cols = {r[0] for r in con.execute("DESCRIBE fct_orders").fetchall()}
        assert {"quarter", "region", "channel", "segment", "net_revenue"} <= cols
        # quarter values look like '2026Q3'
        quarters = {r[0] for r in con.execute("SELECT DISTINCT quarter FROM fct_orders").fetchall()}
        assert "2026Q3" in quarters
    finally:
        con.close()


def test_build_is_idempotent(tmp_path):
    db_path = tmp_path / "w.duckdb"
    seed.build(db_path)
    seed.build(db_path)  # must not raise
    con = duckdb.connect(str(db_path), read_only=True)
    (count,) = con.execute("SELECT COUNT(*) FROM fct_orders").fetchone()
    con.close()
    assert count > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_warehouse_seed.py -v`
Expected: FAIL with `ImportError` / `ModuleNotFoundError` for `backend.warehouse.seed`

- [ ] **Step 3: Write `backend/warehouse/seed.py`**

```python
"""Build a small synthetic analytics warehouse in DuckDB.

Run: python -m backend.warehouse.seed
"""
from __future__ import annotations

import random
from pathlib import Path

import duckdb

from backend.config import RANDOM_SEED, WAREHOUSE_PATH

TABLES = ["dim_region", "fct_orders", "mart_account_health"]

REGIONS = [
    ("North America", "Americas"),
    ("EMEA", "EMEA"),
    ("LATAM", "Americas"),
    ("APAC", "APAC"),
    ("Other", "Other"),
]
REGION_WEIGHTS = [0.42, 0.28, 0.13, 0.14, 0.03]
CHANNELS = ["Direct", "Partner", "Self-serve"]
SEGMENTS = ["Enterprise", "Mid-market", "SMB"]
QUARTERS = ["2026Q1", "2026Q2", "2026Q3"]


def _orders(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    order_id = 1
    for quarter in QUARTERS:
        q_growth = {"2026Q1": 0.9, "2026Q2": 0.95, "2026Q3": 1.0}[quarter]
        for week in range(1, 14):
            for _ in range(rng.randint(60, 90)):
                region = rng.choices(REGIONS, weights=REGION_WEIGHTS)[0][0]
                channel = rng.choice(CHANNELS)
                segment = rng.choice(SEGMENTS)
                base = {"Enterprise": 42000, "Mid-market": 9000, "SMB": 1200}[segment]
                net = round(
                    base * q_growth * (1 + week * 0.01) * rng.uniform(0.6, 1.5), 2
                )
                discount = round(
                    {"Enterprise": 10, "Mid-market": 16, "SMB": 12}[segment]
                    * rng.uniform(0.4, 1.8),
                    1,
                )
                margin = round(max(20.0, 72 - discount * rng.uniform(0.8, 1.4)), 1)
                rows.append(
                    (
                        order_id,
                        f"2026-{QUARTERS.index(quarter) * 3 + 1:02d}-{(week % 28) + 1:02d}",
                        quarter,
                        f"W{week}",
                        region,
                        channel,
                        segment,
                        net,
                        discount,
                        margin,
                    )
                )
                order_id += 1
    return rows


def _account_health(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    for segment in SEGMENTS:
        for discount in (6, 12, 20):
            margin = round(max(30.0, 70 - discount * rng.uniform(1.0, 1.6)), 1)
            accounts = rng.randint(30, 220)
            rows.append((segment, discount, margin, accounts))
    return rows


def build(path: Path | None = None) -> None:
    path = Path(path) if path is not None else WAREHOUSE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    rng = random.Random(RANDOM_SEED)
    con = duckdb.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE dim_region (region VARCHAR, macro_area VARCHAR)"
        )
        con.executemany(
            "INSERT INTO dim_region VALUES (?, ?)",
            [(r, a) for r, a in REGIONS],
        )
        con.execute(
            """
            CREATE TABLE fct_orders (
                order_id BIGINT, order_date VARCHAR, quarter VARCHAR, week VARCHAR,
                region VARCHAR, channel VARCHAR, segment VARCHAR,
                net_revenue DOUBLE, discount_pct DOUBLE, gross_margin_pct DOUBLE
            )
            """
        )
        con.executemany(
            "INSERT INTO fct_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _orders(rng),
        )
        con.execute(
            """
            CREATE TABLE mart_account_health (
                segment VARCHAR, avg_discount INTEGER,
                gross_margin DOUBLE, accounts INTEGER
            )
            """
        )
        con.executemany(
            "INSERT INTO mart_account_health VALUES (?, ?, ?, ?)",
            _account_health(rng),
        )
    finally:
        con.close()


if __name__ == "__main__":
    build()
    print(f"Warehouse built at {WAREHOUSE_PATH}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_warehouse_seed.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Build the real warehouse and commit**

```bash
python -m backend.warehouse.seed
git add backend/warehouse/seed.py tests/test_warehouse_seed.py
git commit -m "feat: synthetic DuckDB warehouse seed"
```

(The `.duckdb` file itself is gitignored.)

---

### Task 3: Warehouse schema context

**Files:**
- Create: `backend/warehouse/schema.py`
- Test: `tests/test_warehouse_schema.py`

**Interfaces:**
- Consumes: `backend.warehouse.seed.build` (in the test fixture), a `duckdb` connection.
- Produces:
  - `SCHEMA_NOTES: str` — constante escrita a mano.
  - `introspect(con: duckdb.DuckDBPyConnection) -> str` — `"tabla(col TYPE, ...)"` una línea por tabla.
  - `schema_context(con: duckdb.DuckDBPyConnection) -> str` — `introspect()` + `SCHEMA_NOTES` + hasta 3 filas de muestra por tabla.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_warehouse_schema.py
import duckdb
import pytest
from backend.warehouse import schema, seed


@pytest.fixture
def con(tmp_path):
    db_path = tmp_path / "w.duckdb"
    seed.build(db_path)
    c = duckdb.connect(str(db_path), read_only=True)
    yield c
    c.close()


def test_introspect_lists_all_tables(con):
    text = schema.introspect(con)
    for table in seed.TABLES:
        assert table in text
    assert "net_revenue" in text


def test_schema_context_includes_notes_and_samples(con):
    ctx = schema.schema_context(con)
    assert schema.SCHEMA_NOTES.strip()[:20] in ctx
    assert "fct_orders" in ctx
    # sample rows section mentions a real region value
    assert "North America" in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_warehouse_schema.py -v`
Expected: FAIL — `backend.warehouse.schema` does not exist

- [ ] **Step 3: Write `backend/warehouse/schema.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_warehouse_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/warehouse/schema.py tests/test_warehouse_schema.py
git commit -m "feat: warehouse schema introspection and notes"
```

---

### Task 4: Safe read-only SQL execution

**Files:**
- Create: `backend/warehouse/db.py`
- Test: `tests/test_warehouse_db.py`

**Interfaces:**
- Consumes: `backend.config` (`WAREHOUSE_PATH`, `SQL_MAX_ROWS`, `SQL_TIMEOUT_S`), `backend.warehouse.seed`.
- Produces:
  - `connect(path=None) -> duckdb.DuckDBPyConnection` — opens `read_only=True`.
  - `class UnsafeSQLError(ValueError)`
  - `run_sql(con, sql: str, *, max_rows: int | None = None, timeout_s: float | None = None) -> dict`
    returns `{"sql": str, "columns": list[str], "rows": list[list], "row_count": int, "truncated": bool}`.
    Raises `UnsafeSQLError` for non-SELECT / multi-statement / DDL-DML.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_warehouse_db.py
import pytest
from backend.warehouse import db, seed


@pytest.fixture
def con(tmp_path):
    p = tmp_path / "w.duckdb"
    seed.build(p)
    c = db.connect(p)
    yield c
    c.close()


def test_select_returns_structured_result(con):
    out = db.run_sql(con, "SELECT region, SUM(net_revenue) AS rev FROM fct_orders GROUP BY 1")
    assert out["columns"] == ["region", "rev"]
    assert out["row_count"] == len(out["rows"])
    assert out["truncated"] is False


@pytest.mark.parametrize("bad", [
    "DELETE FROM fct_orders",
    "UPDATE fct_orders SET net_revenue = 0",
    "DROP TABLE fct_orders",
    "SELECT 1; SELECT 2",
    "INSERT INTO dim_region VALUES ('x', 'y')",
    "ATTACH 'evil.db'",
])
def test_rejects_unsafe_sql(con, bad):
    with pytest.raises(db.UnsafeSQLError):
        db.run_sql(con, bad)


def test_with_cte_is_allowed(con):
    out = db.run_sql(con, "WITH t AS (SELECT 1 AS x) SELECT * FROM t")
    assert out["rows"] == [[1]]


def test_limit_is_injected_and_truncation_flagged(con):
    out = db.run_sql(con, "SELECT * FROM fct_orders", max_rows=5)
    assert out["row_count"] == 5
    assert out["truncated"] is True


def test_explicit_limit_is_respected(con):
    out = db.run_sql(con, "SELECT * FROM fct_orders LIMIT 3", max_rows=5)
    assert out["row_count"] == 3
    assert out["truncated"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_warehouse_db.py -v`
Expected: FAIL — `backend.warehouse.db` does not exist

- [ ] **Step 3: Write `backend/warehouse/db.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_warehouse_db.py -v`
Expected: PASS (all parametrized cases pass)

- [ ] **Step 5: Commit**

```bash
git add backend/warehouse/db.py tests/test_warehouse_db.py
git commit -m "feat: safe read-only SQL runner"
```

---

### Task 5: SSE event types

**Files:**
- Create: `backend/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: nada.
- Produces (all `@dataclass(frozen=True)`, each with `type: str` class attribute and `to_sse() -> str`):
  - `Step(label: str, detail: str = "")`
  - `Thinking(label: str)`
  - `Text(text: str)`
  - `Chart(title: str, meta: str, spec: dict, data: dict)` — `data` is `{"columns": [...], "rows": [...]}`
  - `ErrorEvent(message: str)`
  - `Done(seconds: float)`
  - `Event` = union type alias of the above.
  - `to_sse(event) -> str` module function: `f"event: {event.type}\ndata: {json.dumps(payload)}\n\n"` where `payload` is the dataclass fields minus `type`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_events.py
import json
from backend import events


def test_step_to_sse():
    line = events.to_sse(events.Step(label="sql.query", detail="SELECT 1"))
    assert line.startswith("event: step\n")
    assert line.endswith("\n\n")
    payload = json.loads(line.split("data: ", 1)[1].strip())
    assert payload == {"label": "sql.query", "detail": "SELECT 1"}


def test_chart_to_sse_roundtrips_spec():
    ev = events.Chart(
        title="T", meta="bar", spec={"mark": "bar"},
        data={"columns": ["a"], "rows": [[1]]},
    )
    payload = json.loads(events.to_sse(ev).split("data: ", 1)[1].strip())
    assert payload["spec"] == {"mark": "bar"}
    assert payload["data"]["rows"] == [[1]]


def test_done_type():
    assert events.Done(seconds=1.2).type == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_events.py -v`
Expected: FAIL — `backend.events` does not exist

- [ ] **Step 3: Write `backend/events.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_events.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/events.py tests/test_events.py
git commit -m "feat: SSE event dataclasses"
```

---

### Task 6: Manual agentic loop runner

**Files:**
- Create: `backend/agents/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `backend.config` (`MAX_AGENT_ITERS`, `MAX_TOKENS`), `backend.events`.
- Produces:
  - `get_client() -> anthropic.Anthropic` — module-level singleton, lazily created (so tests can monkeypatch).
  - `Sink = Callable[[events.Event], None]`
  - `@dataclasses.dataclass class ToolCall: name: str; input: dict; result: str; is_error: bool`
  - `@dataclasses.dataclass class AgentResult: final_text: str; messages: list; tool_calls: list[ToolCall]; iterations: int; hit_limit: bool`
  - ```
    run_agent(
        *, model: str, system: str, messages: list[dict],
        tools: list[dict], tool_impls: dict[str, Callable[..., str]],
        sink: Sink, step_label: Callable[[str, dict], events.Step] | None = None,
        max_iters: int | None = None,
    ) -> AgentResult
    ```
    Manual loop over `client.messages.create(...)` with `thinking={"type": "adaptive"}`.
    On `stop_reason == "tool_use"`: for each `tool_use` block, emit `step_label(name, input)`
    (default: `events.Step(label=name)`), call `tool_impls[name](**input)`, append a
    `tool_result` block (`is_error=True` + exception text on raise). On `end_turn`: stop.
    On `pause_turn`: re-append and continue. On reaching `max_iters`: set `hit_limit=True`,
    emit `events.ErrorEvent("agent exceeded ... iterations")`, stop.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm.py
import dataclasses
from backend import events
from backend.agents import llm


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class FakeMessages:
    """Scripted Claude: returns queued responses in order."""
    def __init__(self, script): self._script = list(script); self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._script.pop(0)


class FakeClient:
    def __init__(self, script): self.messages = FakeMessages(script)


def test_runs_tool_then_finishes(monkeypatch):
    script = [
        _Resp("tool_use", [
            _Block(type="tool_use", id="t1", name="run_sql", input={"sql": "SELECT 1"}),
        ]),
        _Resp("end_turn", [_Block(type="text", text="done: 1 row")]),
    ]
    fake = FakeClient(script)
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    seen = []
    result = llm.run_agent(
        model="m", system="s",
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "run_sql"}],
        tool_impls={"run_sql": lambda sql: f"ran {sql}"},
        sink=seen.append,
    )
    assert result.final_text == "done: 1 row"
    assert result.iterations == 2
    assert result.hit_limit is False
    assert [tc.name for tc in result.tool_calls] == ["run_sql"]
    assert result.tool_calls[0].result == "ran SELECT 1"
    assert any(isinstance(e, events.Step) for e in seen)


def test_tool_exception_becomes_error_result(monkeypatch):
    script = [
        _Resp("tool_use", [
            _Block(type="tool_use", id="t1", name="boom", input={}),
        ]),
        _Resp("end_turn", [_Block(type="text", text="recovered")]),
    ]
    fake = FakeClient(script)
    monkeypatch.setattr(llm, "get_client", lambda: fake)

    def boom(): raise ValueError("nope")

    result = llm.run_agent(
        model="m", system="s", messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "boom"}], tool_impls={"boom": boom}, sink=lambda e: None,
    )
    assert result.tool_calls[0].is_error is True
    assert "nope" in result.tool_calls[0].result


def test_hits_iteration_limit(monkeypatch):
    loop_resp = _Resp("tool_use", [
        _Block(type="tool_use", id="t", name="noop", input={}),
    ])

    class Loop:
        messages = type("M", (), {"create": staticmethod(lambda **k: loop_resp)})()

    monkeypatch.setattr(llm, "get_client", lambda: Loop())
    seen = []
    result = llm.run_agent(
        model="m", system="s", messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "noop"}], tool_impls={"noop": lambda: "ok"},
        sink=seen.append, max_iters=3,
    )
    assert result.hit_limit is True
    assert result.iterations == 3
    assert any(isinstance(e, events.ErrorEvent) for e in seen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL — `backend.agents.llm` does not exist

- [ ] **Step 3: Write `backend/agents/llm.py`**

```python
from __future__ import annotations

import dataclasses
import json
from typing import Callable

from backend import events
from backend.config import MAX_AGENT_ITERS, MAX_TOKENS

_client = None


def get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


Sink = Callable[[events.Event], None]


@dataclasses.dataclass
class ToolCall:
    name: str
    input: dict
    result: str
    is_error: bool


@dataclasses.dataclass
class AgentResult:
    final_text: str
    messages: list
    tool_calls: list
    iterations: int
    hit_limit: bool


def _text_of(content) -> str:
    parts = [b.text for b in content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def run_agent(
    *,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_impls: dict[str, Callable[..., str]],
    sink: Sink,
    step_label: Callable[[str, dict], events.Step] | None = None,
    max_iters: int | None = None,
) -> AgentResult:
    max_iters = MAX_AGENT_ITERS if max_iters is None else max_iters
    client = get_client()
    messages = list(messages)
    tool_calls: list[ToolCall] = []
    iterations = 0
    final_text = ""

    while True:
        iterations += 1
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = _text_of(response.content)
            return AgentResult(final_text, messages, tool_calls, iterations, False)

        if response.stop_reason == "pause_turn":
            if iterations >= max_iters:
                break
            continue

        if response.stop_reason == "tool_use":
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            results = []
            for tu in tool_uses:
                label_event = (
                    step_label(tu.name, dict(tu.input))
                    if step_label
                    else events.Step(label=tu.name)
                )
                sink(label_event)
                try:
                    out = tool_impls[tu.name](**tu.input)
                    is_error = False
                except Exception as exc:  # noqa: BLE001 - surfaced to the model
                    out = f"Error: {exc}"
                    is_error = True
                text_out = out if isinstance(out, str) else json.dumps(out)
                tool_calls.append(ToolCall(tu.name, dict(tu.input), text_out, is_error))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": text_out,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
            if iterations >= max_iters:
                break
            continue

        # unknown stop reason: treat as terminal
        final_text = _text_of(response.content)
        return AgentResult(final_text, messages, tool_calls, iterations, False)

    sink(events.ErrorEvent(message=f"agent exceeded {max_iters} iterations"))
    return AgentResult(final_text, messages, tool_calls, iterations, True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/llm.py tests/test_llm.py
git commit -m "feat: manual agentic loop runner with SSE hooks"
```

---

### Task 7: Data agent

**Files:**
- Create: `backend/agents/data_agent.py`
- Test: `tests/test_data_agent.py`

**Interfaces:**
- Consumes: `backend.agents.llm.run_agent` / `AgentResult` / `ToolCall`, `backend.warehouse.db`, `backend.warehouse.schema`, `backend.events`, `backend.config.DATA_AGENT_MODEL`.
- Produces:
  - `@dataclasses.dataclass class DataResult: ok: bool; sql: str; columns: list[str]; rows: list[list]; row_count: int; truncated: bool; notes: str; error: str`
  - `answer_data_question(question: str, sink: llm.Sink, *, con=None) -> DataResult`
    - Builds a `duckdb` connection via `db.connect()` if `con is None`.
    - System prompt = role + `schema.schema_context(con)`.
    - Tools: `get_schema` (emits `Step("schema.lookup")`), `run_sql` (emits `Step("sql.query", detail=<sql>)`).
    - After the loop: takes the last **non-error** `run_sql` ToolCall, parses its JSON result into `DataResult`. If none → `DataResult(ok=False, error="data agent produced no successful query")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_agent.py
import json
import pytest
from backend.agents import data_agent, llm
from backend.warehouse import db, seed


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


class FakeClient:
    def __init__(self, script): self._s = list(script)
    class _M:
        pass
    @property
    def messages(self):
        m = FakeClient._M()
        m.create = lambda **kw: self._s.pop(0)
        return m


@pytest.fixture
def con(tmp_path):
    p = tmp_path / "w.duckdb"
    seed.build(p)
    c = db.connect(p)
    yield c
    c.close()


def test_returns_rows_from_last_successful_query(monkeypatch, con):
    sql = "SELECT region, SUM(net_revenue) AS rev FROM fct_orders GROUP BY 1 ORDER BY 2 DESC"
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="a", name="run_sql", input={"sql": sql})]),
        _Resp("end_turn", [_Block(type="text", text="Revenue is concentrated in North America.")]),
    ]
    monkeypatch.setattr(llm, "get_client", lambda: FakeClient(script))

    seen = []
    result = data_agent.answer_data_question("revenue by region", seen.append, con=con)

    assert result.ok is True
    assert result.columns == ["region", "rev"]
    assert result.row_count > 0
    assert "North America" in result.notes
    assert any(getattr(e, "label", "") == "sql.query" for e in seen)


def test_no_successful_query_returns_not_ok(monkeypatch, con):
    script = [_Resp("end_turn", [_Block(type="text", text="I could not do it.")])]
    monkeypatch.setattr(llm, "get_client", lambda: FakeClient(script))
    result = data_agent.answer_data_question("???", lambda e: None, con=con)
    assert result.ok is False
    assert result.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_agent.py -v`
Expected: FAIL — `backend.agents.data_agent` does not exist

- [ ] **Step 3: Write `backend/agents/data_agent.py`**

```python
from __future__ import annotations

import dataclasses
import json

from backend import events
from backend.agents import llm
from backend.config import DATA_AGENT_MODEL
from backend.warehouse import db, schema

_SYSTEM = """\
You are a senior data analyst with read-only access to a small analytics warehouse.
Given a question, write ONE SQL SELECT that answers it, run it with the run_sql tool,
and then briefly state what the data shows.

{schema}

Guidance:
- Call get_schema only if you need to re-check column names.
- Prefer a single GROUP BY aggregation. Alias output columns in friendly snake_case.
- Keep result sets small (a handful of rows is ideal for charting).
- If run_sql returns an error, fix the SQL and try again.
"""

_TOOLS = [
    {
        "name": "get_schema",
        "description": "Return the warehouse schema, business notes and sample rows.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_sql",
        "description": "Execute a read-only SQL SELECT against the warehouse and return columns + rows as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
]


@dataclasses.dataclass
class DataResult:
    ok: bool
    sql: str = ""
    columns: list = dataclasses.field(default_factory=list)
    rows: list = dataclasses.field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    notes: str = ""
    error: str = ""


def _step_label(name: str, tool_input: dict) -> events.Step:
    if name == "run_sql":
        return events.Step(label="sql.query", detail=tool_input.get("sql", ""))
    if name == "get_schema":
        return events.Step(label="schema.lookup")
    return events.Step(label=name)


def answer_data_question(question: str, sink: llm.Sink, *, con=None) -> DataResult:
    owns_con = con is None
    con = con if con is not None else db.connect()
    try:
        def _get_schema() -> str:
            return schema.schema_context(con)

        def _run_sql(sql: str) -> str:
            return json.dumps(db.run_sql(con, sql))

        result = llm.run_agent(
            model=DATA_AGENT_MODEL,
            system=_SYSTEM.format(schema=schema.schema_context(con)),
            messages=[{"role": "user", "content": question}],
            tools=_TOOLS,
            tool_impls={"get_schema": _get_schema, "run_sql": _run_sql},
            sink=sink,
            step_label=_step_label,
        )
    finally:
        if owns_con:
            con.close()

    last = next(
        (tc for tc in reversed(result.tool_calls) if tc.name == "run_sql" and not tc.is_error),
        None,
    )
    if last is None:
        return DataResult(ok=False, error="data agent produced no successful query", notes=result.final_text)

    payload = json.loads(last.result)
    return DataResult(
        ok=True,
        sql=payload["sql"],
        columns=payload["columns"],
        rows=payload["rows"],
        row_count=payload["row_count"],
        truncated=payload["truncated"],
        notes=result.final_text,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_agent.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/data_agent.py tests/test_data_agent.py
git commit -m "feat: data agent (schema-aware SQL execution)"
```

---

### Task 8: Orchestrator + Vega-Lite validation

**Files:**
- Create: `backend/agents/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `backend.agents.llm`, `backend.agents.data_agent.answer_data_question` / `DataResult`, `backend.events`, `backend.config` (`LLM_MODEL`, `MAX_TOKENS`).
- Produces:
  - `class SpecError(ValueError)`
  - `validate_vega_lite(spec: dict, rows_records: list[dict]) -> dict` — returns a spec with `data.values` filled from `rows_records` when the model left data unbound; raises `SpecError` if the spec has no `$schema`/`mark`|`layer`/`encoding`.
  - `rows_to_records(columns: list[str], rows: list[list]) -> list[dict]`
  - `run(user_message: str, sink: llm.Sink, *, data_fn=answer_data_question) -> None`
    Emits, in order: `Thinking("Reading schema")`, the data agent's own steps (same sink),
    `Text(answer)`, `Chart(...)` (or `ErrorEvent` if the spec is invalid / data agent failed),
    `Done(seconds)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
import json
import pytest
from backend import events
from backend.agents import orchestrator, llm, data_agent


def _dr(**kw):
    base = dict(ok=True, sql="SELECT 1", columns=["region", "rev"],
               rows=[["NA", 8.4], ["EMEA", 6.1]], row_count=2, truncated=False, notes="n")
    base.update(kw)
    return data_agent.DataResult(**base)


class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


def _client_returning(final_json):
    """Fake client: first the tool-use turn calling query_data, then the JSON close-out."""
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="q", name="query_data",
                                  input={"question": "revenue by region"})]),
        _Resp("end_turn", [_Block(type="text", text="Here is the breakdown.")]),
        _Resp("end_turn", [_Block(type="text", text=json.dumps(final_json))]),
    ]

    class C:
        @property
        def messages(self):
            m = type("M", (), {})()
            m.create = lambda **kw: script.pop(0)
            return m
    return C()


def test_rows_to_records():
    recs = orchestrator.rows_to_records(["a", "b"], [[1, 2], [3, 4]])
    assert recs == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_validate_fills_data_values():
    spec = {"$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
            "mark": "bar", "encoding": {"x": {"field": "region"}}}
    out = orchestrator.validate_vega_lite(spec, [{"region": "NA", "rev": 8.4}])
    assert out["data"]["values"] == [{"region": "NA", "rev": 8.4}]


def test_validate_rejects_specless():
    with pytest.raises(orchestrator.SpecError):
        orchestrator.validate_vega_lite({"encoding": {}}, [])


def test_run_emits_chart(monkeypatch):
    final = {
        "answer": "North America leads.",
        "chart_title": "Q3 revenue by region",
        "chart_meta": "bar · fct_orders · 2 rows",
        "vega_lite_spec": {
            "$schema": "https://vega-lite.github.io/schema/vega-lite/v5.json",
            "mark": "bar",
            "encoding": {"x": {"field": "region", "type": "nominal"},
                         "y": {"field": "rev", "type": "quantitative"}},
        },
    }
    monkeypatch.setattr(llm, "get_client", lambda: _client_returning(final))
    seen = []
    orchestrator.run("revenue by region?", seen.append, data_fn=lambda q, s, **k: _dr())

    kinds = [e.type for e in seen]
    assert "text" in kinds and "chart" in kinds and "done" in kinds
    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert chart.spec["data"]["values"][0]["region"] == "NA"
    assert chart.title == "Q3 revenue by region"


def test_run_emits_error_on_bad_spec(monkeypatch):
    final = {"answer": "x", "chart_title": "t", "chart_meta": "m",
             "vega_lite_spec": {"encoding": {}}}
    monkeypatch.setattr(llm, "get_client", lambda: _client_returning(final))
    seen = []
    orchestrator.run("q", seen.append, data_fn=lambda q, s, **k: _dr())
    assert any(isinstance(e, events.ErrorEvent) for e in seen)


def test_run_emits_error_when_data_agent_fails(monkeypatch):
    monkeypatch.setattr(llm, "get_client", lambda: _client_returning({}))
    seen = []
    orchestrator.run("q", seen.append, data_fn=lambda q, s, **k: _dr(ok=False, error="no query"))
    assert any(isinstance(e, events.ErrorEvent) for e in seen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL — `backend.agents.orchestrator` does not exist

- [ ] **Step 3: Write `backend/agents/orchestrator.py`**

```python
from __future__ import annotations

import json
import time

from backend import events
from backend.agents import llm
from backend.agents.data_agent import answer_data_question
from backend.config import LLM_MODEL, MAX_TOKENS

_SYSTEM = """\
You are an analytics orchestrator. You have a data analyst subordinate you reach
via the query_data tool. Your job:
1. Turn the user's question into one or more precise data questions and call query_data.
2. Read the returned columns/rows.
3. Explain the finding in 1-3 short sentences of prose.
4. Design an appropriate Vega-Lite v5 chart for the returned data.

Call query_data at least once before answering. Do not invent numbers.
"""

_QUERY_DATA_TOOL = {
    "name": "query_data",
    "description": "Ask the data analyst a natural-language question about the warehouse. "
    "Returns JSON with sql, columns, rows, row_count.",
    "input_schema": {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
        "additionalProperties": False,
    },
}

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "chart_title": {"type": "string"},
        "chart_meta": {"type": "string"},
        "vega_lite_spec": {"type": "object", "additionalProperties": True},
    },
    "required": ["answer", "chart_title", "chart_meta", "vega_lite_spec"],
    "additionalProperties": False,
}


class SpecError(ValueError):
    """Raised when the model's Vega-Lite spec is structurally invalid."""


def rows_to_records(columns: list[str], rows: list[list]) -> list[dict]:
    return [dict(zip(columns, r)) for r in rows]


def validate_vega_lite(spec: dict, rows_records: list[dict]) -> dict:
    if not isinstance(spec, dict):
        raise SpecError("spec is not an object")
    schema_url = str(spec.get("$schema", ""))
    if "vega-lite" not in schema_url:
        raise SpecError("spec is missing a Vega-Lite $schema")
    if "mark" not in spec and "layer" not in spec:
        raise SpecError("spec has neither 'mark' nor 'layer'")
    has_encoding = "encoding" in spec or any(
        "encoding" in layer for layer in spec.get("layer", []) if isinstance(layer, dict)
    )
    if not has_encoding:
        raise SpecError("spec has no 'encoding'")

    spec = json.loads(json.dumps(spec))  # deep copy
    data = spec.get("data")
    unbound = (
        data is None
        or (isinstance(data, dict) and not data.get("values"))
    )
    if unbound:
        spec["data"] = {"values": rows_records}
    spec.setdefault("width", "container")
    return spec


def run(user_message: str, sink: llm.Sink, *, data_fn=answer_data_question) -> None:
    started = time.monotonic()
    sink(events.Thinking(label="Reading schema"))

    datasets: list = []

    def _query_data(question: str) -> str:
        result = data_fn(question, sink)
        datasets.append(result)
        if not result.ok:
            return json.dumps({"error": result.error})
        return json.dumps(
            {
                "sql": result.sql,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
            }
        )

    agent = llm.run_agent(
        model=LLM_MODEL,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        tools=[_QUERY_DATA_TOOL],
        tool_impls={"query_data": _query_data},
        sink=sink,
        step_label=lambda name, inp: events.Step(
            label="query_data", detail=inp.get("question", "")
        ),
    )

    ok_datasets = [d for d in datasets if d.ok]
    if not ok_datasets:
        msg = datasets[-1].error if datasets else "the data agent returned nothing"
        sink(events.ErrorEvent(message=f"No data available: {msg}"))
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
        return

    dataset = ok_datasets[-1]
    records = rows_to_records(dataset.columns, dataset.rows)

    close_out = llm.get_client().messages.create(
        model=LLM_MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM,
        messages=agent.messages
        + [
            {
                "role": "user",
                "content": "Now produce your final answer and Vega-Lite v5 spec "
                "for this dataset (leave data unbound; it will be injected):\n"
                + json.dumps({"columns": dataset.columns, "rows": dataset.rows[:50]}),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA}},
    )
    text = next(b.text for b in close_out.content if b.type == "text")
    payload = json.loads(text)

    sink(events.Step(label="chart.render", detail="vega-lite v5"))
    try:
        spec = validate_vega_lite(payload["vega_lite_spec"], records)
    except SpecError as exc:
        sink(events.Text(text=payload.get("answer", "")))
        sink(events.ErrorEvent(message=f"Invalid Vega-Lite spec: {exc}"))
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
        return

    sink(events.Text(text=payload["answer"]))
    sink(
        events.Chart(
            title=payload["chart_title"],
            meta=payload["chart_meta"],
            spec=spec,
            data={"columns": dataset.columns, "rows": dataset.rows},
        )
    )
    sink(events.Done(seconds=round(time.monotonic() - started, 1)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator agent with Vega-Lite validation"
```

---

### Task 9: FastAPI SSE endpoint

**Files:**
- Create: `backend/app.py`
- Test: `tests/test_endpoint.py`

**Interfaces:**
- Consumes: `backend.events.to_sse`, `backend.agents.orchestrator.run`.
- Produces:
  - `app = FastAPI(...)`
  - `POST /api/chat` — body `{"session_id": str, "message": str}` → `StreamingResponse(media_type="text/event-stream")`.
    Runs `orchestrator.run` in a worker thread; a `queue.Queue` sink bridges events to the
    stream generator. Any unhandled exception → `ErrorEvent` + `Done`.
  - `GET /` and `GET /{path}` serve files from `frontend/` (`index.html` default).
  - `orchestrator_run` module attribute = `orchestrator.run` (so tests can monkeypatch it).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_endpoint.py
from fastapi.testclient import TestClient
from backend import app as app_module
from backend import events


def _fake_run(message, sink, **kw):
    sink(events.Thinking(label="Reading schema"))
    sink(events.Step(label="sql.query", detail="SELECT 1"))
    sink(events.Text(text="hello"))
    sink(events.Chart(title="T", meta="bar", spec={"mark": "bar"},
                      data={"columns": ["a"], "rows": [[1]]}))
    sink(events.Done(seconds=0.1))


def test_chat_streams_events(monkeypatch):
    monkeypatch.setattr(app_module, "orchestrator_run", _fake_run)
    client = TestClient(app_module.app)
    with client.stream("POST", "/api/chat",
                       json={"session_id": "s1", "message": "hi"}) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = "".join(r.iter_text())
    assert "event: thinking" in body
    assert "event: chart" in body
    assert body.strip().endswith("}")  # last event is 'done' with JSON payload
    assert "event: done" in body


def test_chat_reports_errors(monkeypatch):
    def boom(message, sink, **kw):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(app_module, "orchestrator_run", boom)
    client = TestClient(app_module.app)
    with client.stream("POST", "/api/chat",
                       json={"session_id": "s", "message": "x"}) as r:
        body = "".join(r.iter_text())
    assert "event: error" in body
    assert "kaboom" in body
    assert "event: done" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_endpoint.py -v`
Expected: FAIL — `backend.app` does not exist

- [ ] **Step 3: Write `backend/app.py`**

```python
from __future__ import annotations

import queue
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import events
from backend.agents import orchestrator

orchestrator_run = orchestrator.run  # indirection for tests

_FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="Agent Chat Analytics")


class ChatRequest(BaseModel):
    session_id: str
    message: str


_SENTINEL = object()


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    q: "queue.Queue" = queue.Queue()

    def sink(event: events.Event) -> None:
        q.put(event)

    def worker() -> None:
        try:
            orchestrator_run(req.message, sink)
        except Exception as exc:  # noqa: BLE001 - reported to the client
            q.put(events.ErrorEvent(message=str(exc)))
            q.put(events.Done(seconds=0.0))
        finally:
            q.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = q.get()
            if item is _SENTINEL:
                return
            yield events.to_sse(item)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_FRONTEND / "index.html")


if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_endpoint.py -v`
Expected: PASS (2 passed)

Note: if the `StaticFiles` mount makes the error test flaky because `frontend/` does not
exist yet, create an empty `frontend/index.html` placeholder now (Task 10 overwrites it).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/test_endpoint.py
git commit -m "feat: FastAPI SSE chat endpoint"
```

---

### Task 10: Frontend (single-file UI)

**Files:**
- Create: `frontend/index.html`
- Test: manual (documented smoke check) — no automated test for the static page.

**Interfaces:**
- Consumes: `POST /api/chat` SSE stream with events `thinking`, `step`, `text`, `chart`, `error`, `done`.
- Produces: a rendered page. No exports.

- [ ] **Step 1: Write `frontend/index.html`**

Full file (vanilla JS, reuses the mockup's visual language; single agent thread, no sidebar):

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lumen Analyst</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<style>
  html,body{margin:0;padding:0;height:100%}
  body{background:#faf9f8;color:#1c1b19;font-family:'IBM Plex Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
  *{box-sizing:border-box}
  @keyframes dotpulse{0%,60%,100%{opacity:.25}30%{opacity:1}}
  main{max-width:820px;margin:0 auto;display:flex;flex-direction:column;height:100vh}
  header{display:flex;align-items:center;gap:10px;padding:0 18px;height:52px;border-bottom:1px solid rgba(0,0,0,.06)}
  .title{font-size:13.5px;font-weight:600}
  .badge{display:flex;align-items:center;gap:5px;padding:3px 7px;background:rgba(0,0,0,.045);border-radius:6px;font-size:11px;color:#6b6864}
  .badge span{width:5px;height:5px;border-radius:50%;background:#2f8f7a}
  .thread{flex:1;overflow-y:auto;padding:26px 24px 40px;display:flex;flex-direction:column;gap:26px}
  .user{align-self:flex-end;max-width:78%;padding:10px 14px;background:#ebe8e3;border-radius:14px 14px 4px 14px;font-size:14px;line-height:1.55}
  .agent{display:flex;gap:12px}
  .avatar{flex:none;width:24px;height:24px;border-radius:7px;margin-top:2px;background:#3a53c9}
  .agent-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:12px}
  .trace{border:1px solid rgba(0,0,0,.08);border-radius:9px;background:#fff;overflow:hidden}
  .trace summary{padding:8px 10px;font-size:12px;color:#6b6864;cursor:pointer}
  .trace .steps{border-top:1px solid rgba(0,0,0,.06);padding:9px 12px;display:flex;flex-direction:column;gap:8px;background:#fcfbf9}
  .step-label{font-size:12px;font-weight:500;color:#3a3835}
  .step-detail{margin-top:3px;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.5;color:#7b776f;white-space:pre-wrap;word-break:break-word}
  .para{font-size:14.5px;line-height:1.65;color:#26241f}
  .thinking{display:flex;align-items:center;gap:8px;font-size:13px;color:#8b8781}
  .thinking i{width:5px;height:5px;border-radius:50%;background:#a09b93;animation:dotpulse 1.2s infinite}
  .thinking i:nth-child(2){animation-delay:.2s}.thinking i:nth-child(3){animation-delay:.4s}
  .card{border:1px solid rgba(0,0,0,.09);border-radius:11px;background:#fff;overflow:hidden}
  .card-head{display:flex;align-items:center;gap:10px;padding:9px 13px;border-bottom:1px solid rgba(0,0,0,.06)}
  .card-title{flex:1;font-size:12.5px;font-weight:600}
  .card-meta{font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:#a09b93}
  .tabs{display:flex;gap:2px;padding:2px;background:rgba(0,0,0,.045);border-radius:7px}
  .tabs button{padding:4px 9px;border:none;border-radius:5px;font-size:11.5px;cursor:pointer;background:transparent;color:#7b776f}
  .tabs button.on{background:#fff;color:#1c1b19;font-weight:600}
  .card-body{padding:14px 12px}
  .spec-view{max-height:320px;overflow:auto;font-family:'IBM Plex Mono',monospace;font-size:11.5px;white-space:pre;background:#fbfaf8;padding:12px}
  .err{padding:16px 14px;background:#fdf8f6}
  .err-title{font-size:13px;font-weight:600;color:#8f2018}
  .err-text{margin-top:4px;font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:#8a6560;white-space:pre-wrap}
  table{border-collapse:collapse;font-size:11.5px;font-family:'IBM Plex Mono',monospace}
  th,td{padding:6px 10px;border-bottom:1px solid rgba(0,0,0,.05);text-align:left}
  th{background:#f6f4f1;color:#7b776f;text-transform:uppercase;letter-spacing:.05em}
  .composer{flex:none;padding:0 24px 20px}
  .composer-inner{display:flex;align-items:flex-end;gap:8px;padding:9px 9px 9px 14px;background:#fff;border:1px solid rgba(0,0,0,.1);border-radius:14px}
  textarea{flex:1;border:none;outline:none;resize:none;font-size:14px;line-height:1.5;font-family:inherit;background:transparent;max-height:140px;padding:5px 0}
  .send{flex:none;width:32px;height:32px;border:none;border-radius:9px;cursor:pointer;color:#fff;background:#3a53c9;font-size:15px}
  .send:disabled{background:#c9c4bb}
  .hint{margin-top:7px;text-align:center;font-size:11px;color:#a09b93}
  .empty{margin:14vh auto 0;text-align:center;color:#6b6864;max-width:430px}
  .empty h1{font-size:24px;color:#1c1b19}
</style>
</head>
<body>
<main>
  <header>
    <div class="title">Lumen Analyst</div>
    <div class="badge"><span></span>warehouse · read only</div>
  </header>
  <div class="thread" id="thread">
    <div class="empty" id="empty">
      <h1>What should we look at?</h1>
      <p>Ask about revenue, discounting or margin. Charts come back as Vega-Lite specs, rendered inline.</p>
    </div>
  </div>
  <div class="composer">
    <div class="composer-inner">
      <textarea id="draft" rows="1" placeholder="Ask about the data…"></textarea>
      <button class="send" id="send">↑</button>
    </div>
    <div class="hint">Agent runs read-only SQL and returns Vega-Lite specs. Verify figures before sharing.</div>
  </div>
</main>
<script>
const $ = (s, r = document) => r.querySelector(s);
const thread = $("#thread"), draft = $("#draft"), sendBtn = $("#send");
const SESSION = "s-" + Math.random().toString(36).slice(2);
let busy = false;

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}

function addUser(text) {
  $("#empty")?.remove();
  const n = el("div", "user");
  n.textContent = text;
  thread.appendChild(n);
}

function newAgentBlock() {
  const wrap = el("div", "agent");
  wrap.appendChild(el("div", "avatar"));
  const body = el("div", "agent-body");
  wrap.appendChild(body);
  thread.appendChild(wrap);

  const trace = el("details", "trace");
  trace.appendChild(el("summary", null, "steps"));
  const steps = el("div", "steps");
  trace.appendChild(steps);
  let hasSteps = false;

  const thinking = el("div", "thinking", "<i></i><i></i><i></i><span></span>");
  body.appendChild(thinking);

  const api = {
    thinking(label) { thinking.querySelector("span").textContent = label; },
    step(label, detail) {
      if (!hasSteps) { body.insertBefore(trace, thinking); hasSteps = true; }
      const s = el("div");
      s.appendChild(el("div", "step-label", label));
      if (detail) s.appendChild(el("div", "step-detail", detail.replace(/</g, "&lt;")));
      steps.appendChild(s);
    },
    text(t) {
      thinking.remove();
      body.appendChild(el("div", "para", t.replace(/</g, "&lt;")));
    },
    error(msg) {
      thinking.remove();
      const e = el("div", "card");
      const b = el("div", "err");
      b.appendChild(el("div", "err-title", "Spec failed to render"));
      b.appendChild(el("div", "err-text", msg.replace(/</g, "&lt;")));
      e.appendChild(b);
      body.appendChild(e);
    },
    chart(payload) {
      thinking.remove();
      body.appendChild(buildChartCard(payload));
    },
    done() { thinking.remove(); },
  };
  return api;
}

function buildChartCard({ title, meta, spec, data }) {
  const card = el("div", "card");
  const head = el("div", "card-head");
  head.appendChild(el("div", "card-title", title));
  head.appendChild(el("div", "card-meta", meta));
  const tabs = el("div", "tabs");
  ["Chart", "Spec", "Data"].forEach((name, i) => {
    const b = el("button", i === 0 ? "on" : null, name);
    b.onclick = () => {
      tabs.querySelectorAll("button").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      show(name);
    };
    tabs.appendChild(b);
  });
  head.appendChild(tabs);
  card.appendChild(head);

  const bodyEl = el("div", "card-body");
  card.appendChild(bodyEl);

  function show(name) {
    bodyEl.innerHTML = "";
    if (name === "Chart") {
      const host = el("div");
      bodyEl.appendChild(host);
      vegaEmbed(host, spec, { actions: false, renderer: "svg" })
        .catch(err => { bodyEl.innerHTML =
          '<div class="err"><div class="err-title">Render error</div><div class="err-text">'
          + String(err).replace(/</g, "&lt;") + "</div></div>"; });
    } else if (name === "Spec") {
      bodyEl.appendChild(el("div", "spec-view", JSON.stringify(spec, null, 2).replace(/</g, "&lt;")));
    } else {
      const t = el("table");
      const tr = el("tr");
      data.columns.forEach(c => tr.appendChild(el("th", null, c)));
      t.appendChild(tr);
      data.rows.slice(0, 50).forEach(row => {
        const r = el("tr");
        row.forEach(v => r.appendChild(el("td", null, String(v).replace(/</g, "&lt;"))));
        t.appendChild(r);
      });
      const wrap = el("div");
      wrap.style.overflow = "auto";
      wrap.appendChild(t);
      bodyEl.appendChild(wrap);
    }
  }
  show("Chart");
  return card;
}

async function send() {
  const text = draft.value.trim();
  if (!text || busy) return;
  busy = true; sendBtn.disabled = true; draft.value = "";
  addUser(text);
  const agent = newAgentBlock();
  agent.thinking("Working…");
  thread.scrollTop = thread.scrollHeight;

  let res;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: SESSION, message: text }),
    });
  } catch (e) {
    agent.error("Network error: " + e); busy = false; sendBtn.disabled = false; return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop();
    for (const chunk of chunks) {
      const line = chunk.split("\n");
      const ev = (line.find(l => l.startsWith("event: ")) || "").slice(7).trim();
      const dataLine = line.find(l => l.startsWith("data: "));
      if (!ev || !dataLine) continue;
      const d = JSON.parse(dataLine.slice(6));
      if (ev === "thinking") agent.thinking(d.label);
      else if (ev === "step") agent.step(d.label, d.detail);
      else if (ev === "text") agent.text(d.text);
      else if (ev === "chart") agent.chart(d);
      else if (ev === "error") agent.error(d.message);
      else if (ev === "done") agent.done();
      thread.scrollTop = thread.scrollHeight;
    }
  }
  busy = false; sendBtn.disabled = false;
}

sendBtn.onclick = send;
draft.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
</script>
</body>
</html>
```

- [ ] **Step 2: Smoke check**

```bash
python -m backend.warehouse.seed
uvicorn backend.app:app --reload --port 8000
```

Open `http://localhost:8000`, ask "Q3 revenue by region, chart it". Expected: `steps`
disclosure shows `query_data` → `sql.query` → `chart.render`, prose appears, a bar chart
renders. Toggle the Spec and Data tabs.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: single-file chat UI wired to the SSE backend"
```

---

### Task 11: Integration test + README

**Files:**
- Create: `tests/test_integration.py`
- Create: `README.md`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: everything.
- Produces: `tests/conftest.py` with a session-scoped `warehouse_db` fixture that builds a
  temp warehouse once and points `backend.config.WAREHOUSE_PATH` at it for the whole run.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import importlib
import pytest


@pytest.fixture(scope="session", autouse=True)
def _quiet_anthropic_key(tmp_path_factory):
    # Ensure unit tests never accidentally hit the real API without a key set.
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-not-a-real-key")
    yield
```

- [ ] **Step 2: Write `tests/test_integration.py`**

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-"),
    reason="needs a real ANTHROPIC_API_KEY",
)


def test_end_to_end_revenue_by_region(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_PATH", str(tmp_path / "w.duckdb"))
    import importlib
    from backend import config
    importlib.reload(config)
    from backend.warehouse import seed
    seed.build()

    from backend import events
    from backend.agents import orchestrator
    importlib.reload(orchestrator)

    seen = []
    orchestrator.run("How did Q3 revenue break down by region? Chart it.", seen.append)

    kinds = [e.type for e in seen]
    assert "chart" in kinds, kinds
    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert "vega-lite" in chart.spec["$schema"]
    assert chart.spec["data"]["values"]
```

- [ ] **Step 3: Run the full unit suite**

Run: `pytest -v` (integration test auto-skips without a real key)
Expected: all non-integration tests PASS.

- [ ] **Step 4: Write `README.md`**

```markdown
# Agent Chat Analytics

Multi-agent backend that answers natural-language questions about a small analytics
warehouse and returns a Vega-Lite chart, rendered by a minimal web UI.

- **Orchestrator agent** — turns your question into data questions, then designs a chart.
- **Data agent** — knows the schema, writes and runs read-only SQL against DuckDB.
- **UI** — streams the tool-trace (schema lookup → SQL → chart) and renders the spec inline.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then put your key in ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY=sk-...
python -m backend.warehouse.seed
```

## Run

```bash
uvicorn backend.app:app --port 8000
# open http://localhost:8000
```

## Cost

Every message runs at least two Claude calls (orchestrator loop + close-out) plus the
data agent's loop. Default model is `claude-opus-5`. Set `LLM_MODEL=claude-sonnet-5`
(and/or `DATA_AGENT_MODEL`) to reduce cost.

## Tests

```bash
pytest            # unit tests, no API key needed
ANTHROPIC_API_KEY=sk-... pytest tests/test_integration.py   # live end-to-end
```

## Layout

- `backend/warehouse/` — DuckDB seed, schema introspection, safe SQL runner
- `backend/agents/` — `llm.py` (agentic loop), `data_agent.py`, `orchestrator.py`
- `backend/app.py` — FastAPI SSE endpoint
- `frontend/index.html` — the UI
```

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_integration.py README.md
git commit -m "test: end-to-end integration test; add README"
```

---

## Self-Review

**Spec coverage:**
- Warehouse seed / schema / safe SQL → Tasks 2, 3, 4. ✓
- `agents/llm.py` manual loop + event bus → Task 6. ✓
- Data agent (`get_schema`/`run_sql`, structured return) → Task 7. ✓
- Orchestrator (`query_data` tool, `output_config.format` close-out, `_validate_vega_lite`, event order) → Task 8. ✓
- `events.py` dataclasses + `to_sse` → Task 5. ✓
- `app.py` SSE endpoint, thread + queue sink, static frontend → Task 9. ✓
- `config.py` env overrides → Task 1. ✓
- `frontend/index.html` vanilla JS, tabs Chart/Spec/Data, loading/error, CDN vega → Task 10. (Modal "expand" dropped as YAGNI vs. spec's mention — noted; core flow intact.)
- Error table cases → covered across Tasks 4 (unsafe SQL), 6 (iter limit), 8 (bad spec / data agent fail), 9 (API exception). ✓
- Testing section → Tasks 2–11 each test-first; integration → Task 11. ✓
- Layout → matches spec; `backend/__init__.py` etc. in Task 1. ✓

**Deviation from spec:** the spec's chart card mentions an "expand → modal". Dropped from
Task 10 as non-essential to the end-to-end flow (YAGNI). If wanted, it is an additive
change to `buildChartCard`. Flag to the user.

**Placeholder scan:** no TBD/TODO; every code step has full code. ✓

**Type consistency:** `Sink`, `AgentResult`, `ToolCall`, `DataResult`, `events.*`,
`validate_vega_lite`/`rows_to_records`, `orchestrator_run` indirection — names consistent
across Tasks 5–9. ✓
