# chatkit Core Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the reusable chat/auth/chart infrastructure of the footwear app into an installable `chatkit` package, with the footwear app as a thin consumer, keeping the test suite green at every step.

**Architecture:** Four in-place refactor phases (single widget declaration → unified chat orchestrator → CSS tokenization + JS module split) done inside the current `backend/` + `frontend/` layout, followed by a behavior-free file move into `packages/chatkit/` + `projects/footwear/`. The `Domain` object a project supplies to `create_app(domain)` is the only integration seam.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, DuckDB, Pydantic, pytest, vanilla-JS ES modules (no bundler), Apache ECharts 5, `openai` + `anthropic` SDKs, `google-auth`.

**Spec:** `docs/superpowers/specs/2026-09-06-chatkit-core-extraction-design.md`

## Global Constraints

- Branch: `chatkit-extraction` (already created off `Calzados`).
- Full suite `python3 -m pytest tests/ -q` must be green (currently 143 passed, 1 skipped) at the end of every task. The 1 skip is the live-Anthropic integration test — leave it skipped.
- No new frontend user-facing features until Phase 3 lands (spec §13 Step 0).
- Frontend stays **no build step**: ES modules via `<script type="module">`, no bundler, no npm.
- CDN allowlist unchanged: ECharts + Google Fonts from their current CDNs only.
- Chart ECharts options carry **no colors** — color is the registered theme's job (spec §7).
- KPI values, titles, and `meta.notes` strings are **pre-localized by the domain** — core never translates (spec §16).
- Param name is `heading` everywhere — the REST-only `taric` alias is dropped (spec §5).
- `python` is not on PATH in this environment — always use `python3`.
- `pkill ...; <cmd>` in one Bash call fails (exit 144) — run `pkill`/`kill` as its own call.
- End commit messages with:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01SZ8JNGS6QANGyQMYHgbQf4`

## Out of scope for this plan

Spec §13 Step 5 (build project #2) and Step 6 (cut `chatkit` 0.1.0, repo-split
decision) are follow-up work, not part of this plan. This plan ends with the
footwear app running on the extracted `chatkit` package, monorepo layout, CI
dependency-direction check in place, suite green.

---

## File Structure

### Phase 1 — single widget declaration (still in `backend/`)

- Create `backend/widgets.py` — `Param`, `Widget` dataclasses; `chart_type_param()`; `build_rest_router(widgets, prefix, con_factory)`; `build_tool_set(widgets, con)`; `widget_descriptors(widgets)`.
- Create `backend/services/footwear_widgets.py` — the `WIDGETS: list[Widget]` list for footwear, next to `services/footwear.py`.
- Modify `backend/routers/reports.py` — becomes a 3-line shim that calls `build_rest_router`.
- Modify `backend/agents/tools_footwear.py` — `tool_defs()`/`handlers()` become shims over `build_tool_set`; keep `resolve_footwear_product` as an explicit extra tool.
- Modify `backend/services/footwear.py` — `evolution/country_ranking/product_mix/avg_price/balance` unchanged; only the `meta` dict changes (`is_provisional` → `notes`).
- Test: `tests/test_widgets.py` (new), `tests/test_reports_endpoint.py` + `tests/test_tools_footwear.py` (updated), `tests/test_footwear.py` (meta assertions updated).

### Phase 2 — unified chat orchestrator (still in `backend/`)

- Create `backend/domain.py` — the `Domain` Protocol + `Branding`, `AppConfig`, `TabDescriptor`, `ChartEnvelope` types; a `default_step_label`; a `default_finalize`.
- Create `backend/chat.py` — `run_chat(domain, message, sink, *, history, settings)`.
- Create `backend/sql_domain.py` — `SqlDomain` (wraps `data_agent` + `charts` + the `structured_json` chart mapping).
- Create `backend/footwear_domain.py` — `FootwearDomain`.
- Modify `backend/app.py` — `orchestrator_run` indirection replaced by a module-level `DOMAIN` + `run_chat`.
- Modify `backend/history.py` (new) — move `clean_history` + `MAX_HISTORY_TURNS` out of `backend/agents/orchestrator.py`.
- Delete `backend/agents/orchestrator.py`, `backend/agents/orchestrator_footwear.py`.
- Test: `tests/test_chat.py` (new, replaces `test_orchestrator*.py`), `tests/test_endpoint.py` (updated), `tests/test_sql_domain.py` (new).

### Phase 3 — CSS tokenization + JS module split (still in `frontend/`)

- Create `frontend/chatkit.js` — the ES module: `boot`, `mountChat`, `mountWidgetGrid`, `registerTab`, `mountLogin`.
- Create `frontend/chatkit.css` — all current CSS, hex values replaced by `:root` custom properties.
- Rewrite `frontend/index.html` — ~60 lines: imports `chatkit.js`, calls `boot()`, registers no custom tabs yet.
- Rewrite `frontend/login.html` — ~30 lines: imports `mountLogin`.
- Create `frontend/app.css` — footwear token overrides (currently the accent is already `#3a53c9`, so this is thin).
- Modify `backend/app.py` — add `GET /api/app-config`; add it to `_PUBLIC`; serve `chatkit.js`/`chatkit.css`.
- Create `backend/app_config.py` — `build_app_config(domain, settings)`.
- Test: `tests/test_app_config.py` (new), `tests/test_frontend_smoke.py` (new, headless).

### Phase 4 — file move (pure, zero behavior change)

- Create `packages/chatkit/` with `pyproject.toml`; move core modules per spec §3.1.
- Create `projects/footwear/` per spec §3.2.
- Create `packages/chatkit/chatkit/_demo/` — 2-widget demo domain from the current `backend/warehouse/schema.py` `SCHEMA_NOTES` + `seed.py`.
- Modify all imports.
- Create `.github/` or a `Makefile` check for the dependency-direction rule.
- `git rm --cached backend/warehouse/auth.sqlite backend/warehouse/footwear.duckdb backend/warehouse/warehouse.duckdb`; update `.gitignore`.
- Split `tests/` into `packages/chatkit/tests/` + `projects/footwear/tests/`.

---

## Phase 1 — Single Widget Declaration

### Task 1.1: `Param` and `Widget` dataclasses + `chart_type_param`

**Files:**
- Create: `backend/widgets.py`
- Test: `tests/test_widgets.py`

**Interfaces:**
- Produces:
  - `Param(name: str, type: Literal["enum","int","str","period"], required=False, default=None, enum: list[str] | None = None, ui_label: str | None = None, ui_options: list[dict] | None = None, ui_options_from: str | None = None, ui_option_label: str | None = None)`
  - `Widget(key: str, fn: Callable, params: list[Param], rest_path: str, tool_name: str, tool_description: str, chart_types: list[str] | None = None, span: Literal["full","half"] = "full", in_grid: bool = True)`
  - `chart_type_param(chart_types: list[str]) -> Param` — an enum `Param` named `chart_type`, not required, `default=chart_types[0]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_widgets.py
from backend.widgets import Param, Widget, chart_type_param


def _noop(con):
    return {}


def test_widget_defaults():
    w = Widget(key="evolution", fn=_noop, params=[], rest_path="/evolution",
               tool_name="market_overview", tool_description="d")
    assert w.span == "full"
    assert w.in_grid is True
    assert w.chart_types is None


def test_chart_type_param_is_enum_with_first_as_default():
    p = chart_type_param(["line", "bar"])
    assert p.name == "chart_type"
    assert p.type == "enum"
    assert p.enum == ["line", "bar"]
    assert p.required is False
    assert p.default == "line"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_widgets.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.widgets'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/widgets.py
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Literal

ParamType = Literal["enum", "int", "str", "period"]


@dataclasses.dataclass(frozen=True)
class Param:
    name: str
    type: ParamType
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    ui_label: str | None = None
    ui_options: list[dict] | None = None
    ui_options_from: str | None = None
    ui_option_label: str | None = None


@dataclasses.dataclass(frozen=True)
class Widget:
    key: str
    fn: Callable[..., dict]
    params: list[Param]
    rest_path: str
    tool_name: str
    tool_description: str
    chart_types: list[str] | None = None
    span: Literal["full", "half"] = "full"
    in_grid: bool = True


def chart_type_param(chart_types: list[str]) -> Param:
    return Param(
        name="chart_type",
        type="enum",
        required=False,
        default=chart_types[0],
        enum=list(chart_types),
        ui_label=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_widgets.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/widgets.py tests/test_widgets.py
git commit -m "feat(widgets): Param/Widget descriptors + chart_type_param"
```

---

### Task 1.2: `widget_descriptors` — the frontend/app-config view

**Files:**
- Modify: `backend/widgets.py`
- Test: `tests/test_widgets.py`

**Interfaces:**
- Produces: `widget_descriptors(widgets: list[Widget]) -> dict[str, dict]` — maps `widget.key` to `{"rest_path": str, "span": str, "params": [ {name,type,required,default,enum,ui_label,ui_options,ui_options_from,ui_option_label} ]}`. Omits `chart_type` params (LLM-only, not a filter). `rest_path` is the value passed in (caller prefixes it).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_widgets.py
from backend.widgets import widget_descriptors


def test_widget_descriptors_shape():
    w = Widget(
        key="evolution", fn=_noop, rest_path="/api/v1/reports/footwear/evolution",
        tool_name="market_overview", tool_description="d", span="full",
        params=[
            Param("flow", "enum", required=True, default="IMPORT",
                  enum=["IMPORT", "EXPORT"], ui_label="Flujo",
                  ui_options=[{"value": "IMPORT", "label": "Importaciones"}]),
            Param("months", "int", default=24, ui_label="Meses"),
            chart_type_param(["line", "bar"]),
        ],
    )
    d = widget_descriptors([w])["evolution"]
    assert d["rest_path"] == "/api/v1/reports/footwear/evolution"
    assert d["span"] == "full"
    names = [p["name"] for p in d["params"]]
    assert names == ["flow", "months"]          # chart_type dropped
    assert d["params"][0]["ui_options"][0]["label"] == "Importaciones"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_widgets.py::test_widget_descriptors_shape -q`
Expected: FAIL — `ImportError: cannot import name 'widget_descriptors'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to backend/widgets.py

def _param_dict(p: Param) -> dict:
    return {
        "name": p.name, "type": p.type, "required": p.required,
        "default": p.default, "enum": p.enum, "ui_label": p.ui_label,
        "ui_options": p.ui_options, "ui_options_from": p.ui_options_from,
        "ui_option_label": p.ui_option_label,
    }


def widget_descriptors(widgets: list[Widget]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for w in widgets:
        out[w.key] = {
            "rest_path": w.rest_path,
            "span": w.span,
            "params": [
                _param_dict(p) for p in w.params if p.name != "chart_type"
            ],
        }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_widgets.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/widgets.py tests/test_widgets.py
git commit -m "feat(widgets): widget_descriptors for app-config"
```

---

### Task 1.3: `build_rest_router` — generate the REST routes

**Files:**
- Modify: `backend/widgets.py`
- Test: `tests/test_widgets.py`

**Interfaces:**
- Consumes: `Widget`, `Param` (Task 1.1)
- Produces: `build_rest_router(widgets: list[Widget], *, prefix: str, con_factory: Callable[[], Any]) -> fastapi.APIRouter`. Each widget becomes `GET {prefix}{rest_path}`; query params come from `widget.params` (name, python type from `Param.type`: enum/str→str, int→int, period→str; `required`/`default` respected); handler calls `widget.fn(con, **kwargs)` with `con` from `con_factory()` (a generator dependency that closes the connection). Enum params are validated against `Param.enum` — a bad value returns HTTP 422.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_widgets.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.widgets import build_rest_router


def test_build_rest_router_calls_fn_with_params():
    seen = {}

    def evo(con, *, flow, months=24):
        seen["flow"] = flow
        seen["months"] = months
        return {"widget": "evolution", "title": "t", "echarts": {}, "kpis": [], "meta": {}}

    w = Widget(key="evolution", fn=evo, rest_path="/evolution",
               tool_name="mo", tool_description="d",
               params=[Param("flow", "enum", required=True, enum=["IMPORT", "EXPORT"]),
                       Param("months", "int", default=24)])
    app = FastAPI()
    app.include_router(build_rest_router([w], prefix="/r", con_factory=lambda: None))
    client = TestClient(app)

    r = client.get("/r/evolution", params={"flow": "IMPORT", "months": 6})
    assert r.status_code == 200
    assert seen == {"flow": "IMPORT", "months": 6}

    assert client.get("/r/evolution", params={"flow": "NOPE"}).status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_widgets.py::test_build_rest_router_calls_fn_with_params -q`
Expected: FAIL — `ImportError: cannot import name 'build_rest_router'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to backend/widgets.py
from typing import Annotated
import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query


_PY_TYPE = {"enum": str, "str": str, "period": str, "int": int}


def _dependency(con_factory):
    def _dep():
        con = con_factory()
        try:
            yield con
        finally:
            close = getattr(con, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
    return _dep


def build_rest_router(widgets, *, prefix, con_factory):
    router = APIRouter(prefix=prefix)
    dep = _dependency(con_factory)

    for w in widgets:
        router.add_api_route(
            w.rest_path,
            _make_endpoint(w, dep),
            methods=["GET"],
            name=w.key,
        )
    return router


def _make_endpoint(w, dep):
    params = [p for p in w.params if p.name != "chart_type"]

    def endpoint(request_params: dict = Depends(_query_parser(w)), con=Depends(dep)):
        return w.fn(con, **request_params)

    return endpoint


def _query_parser(w):
    def parse(**kwargs):
        out = {}
        for p in w.params:
            if p.name not in kwargs:
                continue
            val = kwargs[p.name]
            if val is None:
                if p.required:
                    raise HTTPException(422, f"missing required param {p.name}")
                continue
            if p.type == "enum" and p.enum and val not in p.enum:
                raise HTTPException(422, f"{p.name} must be one of {p.enum}")
            out[p.name] = val
        for p in w.params:
            if p.required and p.name not in out:
                raise HTTPException(422, f"missing required param {p.name}")
        return out

    # build a signature FastAPI can introspect
    import inspect

    sig_params = []
    for p in w.params:
        if p.name == "chart_type":
            continue
        py = _PY_TYPE[p.type]
        default = ... if p.required else p.default
        sig_params.append(
            inspect.Parameter(
                p.name, inspect.Parameter.KEYWORD_ONLY,
                default=Query(default), annotation=py | None if not p.required else py,
            )
        )
    parse.__signature__ = inspect.Signature(sig_params)
    return parse
```

> Note for the implementer: FastAPI needs a real signature to build query
> params. The `inspect.Signature` assignment above is the mechanism. If the
> `X | None` annotation with `Query()` default fights FastAPI's validation,
> fall back to `typing.Optional[py]` and `Query(default)`. Verify the 422 path
> works for both missing-required and bad-enum before moving on.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_widgets.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/widgets.py tests/test_widgets.py
git commit -m "feat(widgets): build_rest_router generates report endpoints"
```

---

### Task 1.4: `build_tool_set` — generate the chat tools

**Files:**
- Modify: `backend/widgets.py`
- Test: `tests/test_widgets.py`

**Interfaces:**
- Consumes: `Widget`, `Param`
- Produces: `build_tool_set(widgets: list[Widget], con) -> dict` with keys `"defs": list[dict]` (Anthropic tool schema: `name`, `description`, `input_schema` with `type: object`, `properties` from params, `required` list, `additionalProperties: False`) and `"handlers": dict[str, Callable[..., str]]` (each `lambda **kw: json.dumps(widget.fn(con, **coerced_kw))`, ints coerced via `int()`). `chart_type` params appear in the schema as an enum with the widget's `chart_types`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_widgets.py
import json
from backend.widgets import build_tool_set


def test_build_tool_set_defs_and_handlers():
    def mix(con, *, flow, chart_type=None):
        return {"widget": "mix", "flow": flow, "chart_type": chart_type}

    w = Widget(key="mix", fn=mix, rest_path="/mix", tool_name="product_mix",
               tool_description="reparto por tipo",
               chart_types=["pie", "bar"],
               params=[Param("flow", "enum", required=True, enum=["IMPORT", "EXPORT"]),
                       chart_type_param(["pie", "bar"])])
    ts = build_tool_set([w], con=None)

    d = ts["defs"][0]
    assert d["name"] == "product_mix"
    assert d["input_schema"]["properties"]["flow"]["enum"] == ["IMPORT", "EXPORT"]
    assert d["input_schema"]["properties"]["chart_type"]["enum"] == ["pie", "bar"]
    assert d["input_schema"]["required"] == ["flow"]

    out = json.loads(ts["handlers"]["product_mix"](flow="IMPORT", chart_type="bar"))
    assert out == {"widget": "mix", "flow": "IMPORT", "chart_type": "bar"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_widgets.py::test_build_tool_set_defs_and_handlers -q`
Expected: FAIL — `ImportError: cannot import name 'build_tool_set'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to backend/widgets.py
import json

_JSON_TYPE = {"enum": "string", "str": "string", "period": "string", "int": "integer"}


def _tool_def(w: Widget) -> dict:
    props: dict = {}
    required: list[str] = []
    for p in w.params:
        schema = {"type": _JSON_TYPE[p.type]}
        if p.enum:
            schema["enum"] = list(p.enum)
        if p.ui_label:
            schema["description"] = p.ui_label
        props[p.name] = schema
        if p.required:
            required.append(p.name)
    return {
        "name": w.tool_name,
        "description": w.tool_description,
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
    }


def _handler(w: Widget, con):
    int_params = {p.name for p in w.params if p.type == "int"}

    def run(**kw):
        coerced = {k: (int(v) if k in int_params and v is not None else v)
                   for k, v in kw.items()}
        return json.dumps(w.fn(con, **coerced))

    return run


def build_tool_set(widgets: list[Widget], con) -> dict:
    return {
        "defs": [_tool_def(w) for w in widgets],
        "handlers": {w.tool_name: _handler(w, con) for w in widgets},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_widgets.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/widgets.py tests/test_widgets.py
git commit -m "feat(widgets): build_tool_set generates chat tools from widgets"
```

---

### Task 1.5: footwear `WIDGETS` list + envelope `notes` change

**Files:**
- Create: `backend/services/footwear_widgets.py`
- Modify: `backend/services/footwear.py` (only the `meta` dicts)
- Test: `tests/test_footwear.py` (meta assertions), `tests/test_footwear_widgets.py` (new)

**Interfaces:**
- Consumes: `Widget`, `Param`, `chart_type_param`; `backend.services.footwear` functions.
- Produces: `backend.services.footwear_widgets.WIDGETS: list[Widget]` (keys `evolution`, `countries`, `mix`, `price`, `balance`), and `REST_PREFIX = "/api/v1/reports/footwear"`.
- `ChartEnvelope.meta` no longer has `is_provisional: bool`; instead `notes: list[str]` (contains `"incluye datos provisionales"` when the last period is provisional).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_footwear_widgets.py
from backend.services.footwear_widgets import WIDGETS, REST_PREFIX
from backend.widgets import build_tool_set


def test_widget_keys_and_tool_names():
    keys = {w.key for w in WIDGETS}
    assert keys == {"evolution", "countries", "mix", "price", "balance"}
    names = {w.tool_name for w in WIDGETS}
    assert "footwear_market_overview" in names


def test_every_widget_param_named_heading_not_taric():
    for w in WIDGETS:
        assert all(p.name != "taric" for p in w.params)


def test_tool_set_builds():
    ts = build_tool_set(WIDGETS, con=None)
    assert len(ts["defs"]) == 5
```

```python
# add to tests/test_footwear.py — replace the is_provisional assertion
def test_evolution_notes_flag_provisional(con):
    _insert(
        con,
        _flow(period="2024-11", year=2024, month=11, value_eur=1_000_000),
        _flow(period="2024-12", year=2024, month=12, value_eur=1_000_000,
              is_provisional=True),
    )
    out = footwear.evolution(con, flow="IMPORT", heading="64", months=12)
    assert "incluye datos provisionales" in out["meta"]["notes"]
    assert "is_provisional" not in out["meta"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_footwear_widgets.py tests/test_footwear.py::test_evolution_notes_flag_provisional -q`
Expected: FAIL — module missing; `meta` still has `is_provisional`.

- [ ] **Step 3: Write minimal implementation**

In `backend/services/footwear.py`, in every builder that sets
`meta: {"is_provisional": ...}`, replace with:

```python
"meta": {
    "unit": "EUR",
    "granularity": "monthly",
    "notes": (["incluye datos provisionales"] if provisional else []),
},
```

(`country_ranking`/`product_mix` had `granularity: "range"` and no provisional
flag — give them `"notes": []`.)

```python
# backend/services/footwear_widgets.py
from __future__ import annotations

from backend.services import footwear
from backend.widgets import Param, Widget, chart_type_param

REST_PREFIX = "/api/v1/reports/footwear"

_FLOW = Param(
    "flow", "enum", required=True, default="IMPORT", enum=["IMPORT", "EXPORT"],
    ui_label="Flujo",
    ui_options=[{"value": "IMPORT", "label": "Importaciones"},
                {"value": "EXPORT", "label": "Exportaciones"}],
)
_HEADING = Param(
    "heading", "str", default="64", ui_label="Partida",
    ui_options_from="headings", ui_option_label="{code} — {description}",
)
_MONTHS = Param("months", "int", default=24, ui_label="Meses")

WIDGETS: list[Widget] = [
    Widget(
        key="evolution", fn=footwear.evolution, rest_path="/evolution",
        tool_name="footwear_market_overview",
        tool_description=(
            "Evolución mensual del valor de importaciones/exportaciones de "
            "calzado, con variación interanual. Para 'tendencia', 'evolución'."
        ),
        params=[_FLOW, _HEADING, _MONTHS, chart_type_param(["line", "bar"])],
        chart_types=["line", "bar"], span="full",
    ),
    Widget(
        key="countries", fn=footwear.country_ranking, rest_path="/countries",
        tool_name="footwear_top_partners",
        tool_description=(
            "Ranking de países origen/destino por valor. Para 'de dónde "
            "importamos', 'a dónde exportamos', 'principales socios'."
        ),
        params=[_FLOW, _HEADING,
                Param("top_n", "int", default=10, ui_label="Top"),
                chart_type_param(["bar", "pie"])],
        chart_types=["bar", "pie"], span="full",
    ),
    Widget(
        key="mix", fn=footwear.product_mix, rest_path="/product-mix",
        tool_name="footwear_product_mix",
        tool_description=(
            "Reparto del valor por tipo de calzado (partidas 6401–6406)."
        ),
        params=[_FLOW, chart_type_param(["pie", "bar"])],
        chart_types=["pie", "bar"], span="half",
    ),
    Widget(
        key="price", fn=footwear.avg_price, rest_path="/avg-price",
        tool_name="footwear_avg_price",
        tool_description="Precio medio implícito en €/kg a lo largo del tiempo.",
        params=[_FLOW, _HEADING,
                Param("country", "str", ui_label="País"),
                _MONTHS, chart_type_param(["line", "bar"])],
        chart_types=["line", "bar"], span="half",
    ),
    Widget(
        key="balance", fn=footwear.balance, rest_path="/balance",
        tool_name="footwear_trade_balance",
        tool_description=(
            "Saldo comercial mensual (exportaciones − importaciones) y acumulado."
        ),
        params=[_HEADING, _MONTHS, chart_type_param(["bar", "line"])],
        chart_types=["bar", "line"], span="full",
    ),
]
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_footwear_widgets.py tests/test_footwear.py -q`
Expected: PASS (fix any other `is_provisional` assertions in `test_footwear.py` to check `meta["notes"]` instead)

- [ ] **Step 5: Commit**

```bash
git add backend/services/footwear_widgets.py backend/services/footwear.py tests/test_footwear_widgets.py tests/test_footwear.py
git commit -m "feat(footwear): WIDGETS list; meta.is_provisional -> meta.notes"
```

---

### Task 1.6: rewire `routers/reports.py` and `agents/tools_footwear.py` as shims

**Files:**
- Modify: `backend/routers/reports.py`
- Modify: `backend/agents/tools_footwear.py`
- Modify: `backend/app.py` (import path if needed)
- Test: `tests/test_reports_endpoint.py`, `tests/test_tools_footwear.py` (both should still pass with minimal edits)

**Interfaces:**
- Consumes: `WIDGETS`, `REST_PREFIX` (Task 1.5); `build_rest_router`, `build_tool_set` (Tasks 1.3–1.4).
- Produces: `backend.routers.reports.router` (unchanged name); `backend.agents.tools_footwear.tool_defs() -> list[dict]`, `.handlers(con) -> dict`, `.REPORT_TOOLS: set[str]` (unchanged names). `tools_footwear` still adds `resolve_footwear_product` (def + handler) on top of the generated set.

- [ ] **Step 1: Update the tests first (they encode the old param name `taric`)**

In `tests/test_reports_endpoint.py`, change every `params={"taric": ...}` to
`params={"heading": ...}`. Keep one test asserting the default still works with
no `heading`.

Run: `python3 -m pytest tests/test_reports_endpoint.py -q`
Expected: FAIL — routes still expect `taric` / `get_footwear_con` override gone.

- [ ] **Step 2: Implement the shims**

```python
# backend/routers/reports.py
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
```

```python
# backend/agents/tools_footwear.py
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
        "'botas de agua', 'de cuero') a su partida TARIC de 4 dígitos."
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
```

Update `tests/test_reports_endpoint.py`'s fixture: it monkeypatched
`reports.get_footwear_con` — that no longer exists. Point the connection at the
test duckdb by setting `config.DATACOMEX_PATH` to `tmp_path / "dc.duckdb"` in the
fixture (write it to disk first) instead of a dependency override.

- [ ] **Step 3: Run the affected suites**

Run: `python3 -m pytest tests/test_reports_endpoint.py tests/test_tools_footwear.py tests/test_orchestrator_footwear.py -q`
Expected: PASS

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (143 passed, 1 skipped) — investigate any regression before committing.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/reports.py backend/agents/tools_footwear.py tests/
git commit -m "refactor(footwear): reports router + chat tools generated from WIDGETS"
```

---

## Phase 2 — Unified Chat Orchestrator

### Task 2.1: move `clean_history` into `backend/history.py`

**Files:**
- Create: `backend/history.py`
- Modify: `backend/agents/orchestrator.py`, `backend/agents/orchestrator_footwear.py` (imports)
- Test: `tests/test_history.py` (new — move the relevant cases from wherever `clean_history` is currently tested)

**Interfaces:**
- Produces: `backend.history.clean_history(turns) -> list[dict]`; `backend.history.MAX_HISTORY_TURNS: int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history.py
from backend.history import clean_history, MAX_HISTORY_TURNS


def test_drops_non_user_assistant_and_empty():
    turns = [{"role": "system", "content": "x"},
             {"role": "user", "content": " "},
             {"role": "user", "content": "hi"},
             {"role": "assistant", "content": "yo"}]
    assert clean_history(turns) == [{"role": "user", "content": "hi"},
                                    {"role": "assistant", "content": "yo"}]


def test_caps_to_max_turns():
    turns = [{"role": "user", "content": f"m{i}"} if i % 2 == 0
             else {"role": "assistant", "content": f"a{i}"} for i in range(20)]
    assert len(clean_history(turns)) <= MAX_HISTORY_TURNS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_history.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.history'`

- [ ] **Step 3: Move the code**

Cut `clean_history` and `MAX_HISTORY_TURNS` from `backend/agents/orchestrator.py`
into `backend/history.py` verbatim. In `orchestrator.py` and
`orchestrator_footwear.py` replace the definition/import with
`from backend.history import clean_history, MAX_HISTORY_TURNS`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_history.py tests/test_orchestrator.py tests/test_orchestrator_footwear.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/history.py backend/agents/orchestrator.py backend/agents/orchestrator_footwear.py tests/test_history.py
git commit -m "refactor: move clean_history into backend/history.py"
```

---

### Task 2.2: the `Domain` protocol + envelope types + defaults

**Files:**
- Create: `backend/domain.py`
- Test: `tests/test_domain.py`

**Interfaces:**
- Produces:
  - Dataclasses `Branding(name, short_name, badge, favicon)`, `TabDescriptor(id, label, icon, kind, widgets=None, filters=None)`, `AppConfig(branding, example_prompts, echarts_themes, tabs)`.
  - `Domain` Protocol with attributes/methods per spec §4: `settings`, `app_config()`, `system_prompt: str`, `prose_closeout_instruction: str`, `open_connection()`, `widgets() -> list[Widget]`, `extra_tools() -> dict | None`, `web_dir() -> str`, `finalize(agent, con) -> dict | None`, `step_label(name, tool_input) -> events.Step | None`, `report_prefix() -> str | None`, `filter_options(con) -> dict`.
  - `default_step_label(name, tool_input) -> events.Step` — `"name · k=v · k=v"`.
  - `default_finalize(agent, con, widgets) -> dict | None` — parse the last successful widget-tool result (a `ChartEnvelope` JSON) from `agent.tool_calls`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_domain.py
import json
from backend.domain import default_step_label, default_finalize, Branding
from backend.agents.llm import AgentResult, ToolCall


def test_default_step_label_formats_kv():
    s = default_step_label("footwear_top_partners", {"flow": "IMPORT", "top_n": 5})
    assert s.label == "footwear_top_partners"
    assert "flow=IMPORT" in s.detail and "top_n=5" in s.detail


def test_default_finalize_returns_last_report_envelope():
    env = {"widget": "countries", "title": "t", "echarts": {}, "kpis": [], "meta": {}}
    agent = AgentResult(
        final_text="", messages=[], iterations=1, hit_limit=False,
        tool_calls=[
            ToolCall("footwear_top_partners", {}, json.dumps(env), is_error=False),
        ],
    )
    assert default_finalize(agent, con=None, report_tool_names={"footwear_top_partners"}) == env


def test_branding_is_a_dataclass():
    b = Branding(name="X", short_name="x", badge="b", favicon="🥾")
    assert b.name == "X"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_domain.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.domain'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/domain.py
from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable, Literal, Protocol

from backend import events
from backend.widgets import Widget


@dataclasses.dataclass(frozen=True)
class Branding:
    name: str
    short_name: str
    badge: str
    favicon: str


@dataclasses.dataclass(frozen=True)
class TabDescriptor:
    id: str
    label: str
    icon: str
    kind: Literal["widget_grid", "custom"]
    widgets: list[str] | None = None
    filters: list[str] | None = None


@dataclasses.dataclass(frozen=True)
class AppConfig:
    branding: Branding
    example_prompts: list[str]
    echarts_themes: list[str]
    tabs: list[TabDescriptor]


class Domain(Protocol):
    settings: Any
    system_prompt: str
    prose_closeout_instruction: str

    def app_config(self) -> AppConfig: ...
    def open_connection(self) -> Any: ...
    def widgets(self) -> list[Widget]: ...
    def extra_tools(self) -> dict | None: ...
    def web_dir(self) -> str: ...
    def finalize(self, agent, con) -> dict | None: ...
    def step_label(self, name: str, tool_input: dict) -> events.Step | None: ...
    def report_prefix(self) -> str | None: ...
    def filter_options(self, con) -> dict: ...


def default_step_label(name: str, tool_input: dict) -> events.Step:
    detail = " · ".join(f"{k}={v}" for k, v in tool_input.items() if v is not None)
    return events.Step(label=name, detail=detail)


def default_finalize(agent, con, *, report_tool_names: set[str]) -> dict | None:
    for tc in reversed(agent.tool_calls):
        if tc.name in report_tool_names and not tc.is_error:
            try:
                return json.loads(tc.result)
            except (json.JSONDecodeError, TypeError):
                return None
    return None
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_domain.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domain.py tests/test_domain.py
git commit -m "feat(domain): Domain protocol, envelope types, default hooks"
```

---

### Task 2.3: `run_chat` — the unified orchestrator

**Files:**
- Create: `backend/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: `Domain` (2.2), `clean_history` (2.1), `backend.agents.llm` (`run_agent`, `stream_text`), `backend.events`.
- Produces: `run_chat(domain: Domain, user_message: str, sink, *, history=None) -> None`. Emits, in order: `Thinking` → agent tool steps → `Delta`* (streamed prose) → `Step("chart.render")` → `Text(final prose)` → `Chart` (if `domain.finalize` returned an envelope) → `Done`. When `finalize` returns `None`: emits `Text` then `Done` (no `ErrorEvent` — matches current footwear behavior). Sets `Chart.data` from `envelope.get("data")` or `{"columns": [], "rows": []}`. Honors `agent.hit_limit` by appending a `note` to `meta.notes` ("respuesta truncada: se alcanzó el límite de pasos").

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat.py
import json
import backend.chat as chat_mod
from backend import events
from backend.agents.llm import AgentResult, ToolCall
from backend.domain import Branding, AppConfig


class FakeDomain:
    settings = None
    system_prompt = "sys"
    prose_closeout_instruction = "resume"

    def app_config(self):
        return AppConfig(Branding("X", "x", "b", "🥾"), [], ["lumen"], [])

    def open_connection(self):
        return None

    def widgets(self):
        return []

    def extra_tools(self):
        return {"defs": [], "handlers": {}}

    def report_prefix(self):
        return None

    def filter_options(self, con):
        return {}

    def web_dir(self):
        return "."

    def step_label(self, name, ti):
        return None

    def finalize(self, agent, con):
        return {"widget": "w", "title": "t", "echarts": {"x": 1}, "kpis": [],
                "meta": {"notes": []}, "data": {"columns": ["a"], "rows": [[1]]}}


def test_run_chat_emits_ordered_events(monkeypatch):
    events_seen = []

    def fake_run_agent(**kw):
        return AgentResult(final_text="", messages=[], tool_calls=[], iterations=1,
                           hit_limit=False)

    def fake_stream_text(**kw):
        yield "Las exporta"
        yield "ciones subieron."

    monkeypatch.setattr(chat_mod.llm, "run_agent", fake_run_agent)
    monkeypatch.setattr(chat_mod.llm, "stream_text", fake_stream_text)

    chat_mod.run_chat(FakeDomain(), "¿cómo van las expo?", events_seen.append)

    kinds = [e.type for e in events_seen]
    assert kinds[0] == "thinking"
    assert "delta" in kinds
    assert kinds[-1] == "done"
    chart = next(e for e in events_seen if e.type == "chart")
    assert chart.data == {"columns": ["a"], "rows": [[1]]}
    text = next(e for e in events_seen if e.type == "text")
    assert text.text == "Las exportaciones subieron."


def test_run_chat_no_envelope_still_finishes(monkeypatch):
    d = FakeDomain()
    d.finalize = lambda agent, con: None
    monkeypatch.setattr(chat_mod.llm, "run_agent",
                        lambda **kw: AgentResult("", [], [], 1, False))
    monkeypatch.setattr(chat_mod.llm, "stream_text", lambda **kw: iter(["ok"]))
    seen = []
    chat_mod.run_chat(d, "hi", seen.append)
    assert [e.type for e in seen][-1] == "done"
    assert not any(e.type == "chart" for e in seen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_chat.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.chat'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/chat.py
from __future__ import annotations

import time

from backend import events
from backend.agents import llm
from backend.config import LLM_MODEL
from backend.domain import Domain, default_step_label
from backend.history import clean_history


def run_chat(domain: Domain, user_message: str, sink, *, history=None) -> None:
    started = time.monotonic()
    con = domain.open_connection()
    try:
        prior = clean_history(history)
        sink(events.Thinking(label="Consultando datos"))

        tools = domain.widgets_tool_set(con) if hasattr(domain, "widgets_tool_set") else None
        extra = domain.extra_tools() or {"defs": [], "handlers": {}}
        from backend.widgets import build_tool_set
        wt = build_tool_set(domain.widgets(), con)
        defs = extra["defs"] + wt["defs"]
        handlers = {**extra["handlers"], **wt["handlers"]}

        def _label(name, ti):
            return domain.step_label(name, ti) or default_step_label(name, ti)

        agent = llm.run_agent(
            model=LLM_MODEL, system=domain.system_prompt,
            messages=prior + [{"role": "user", "content": user_message}],
            tools=defs, tool_impls=handlers, sink=sink, step_label=_label,
        )

        envelope = domain.finalize(agent, con)

        answer = ""
        closeout = [{"role": "user", "content": domain.prose_closeout_instruction}]
        for piece in llm.stream_text(
            model=LLM_MODEL, system=domain.system_prompt,
            messages=agent.messages + closeout,
        ):
            answer += piece
            sink(events.Delta(text=piece))
        answer = answer.strip() or agent.final_text or "Sin respuesta."

        if envelope is None:
            sink(events.Text(text=answer))
            sink(events.Done(seconds=round(time.monotonic() - started, 1)))
            return

        meta = envelope.setdefault("meta", {})
        notes = meta.setdefault("notes", [])
        if agent.hit_limit:
            notes.append("respuesta truncada: se alcanzó el límite de pasos")

        sink(events.Step(label="chart.render", detail="echarts v5"))
        sink(events.Text(text=answer))
        sink(events.Chart(
            title=envelope.get("title", "Informe"),
            meta=" · ".join(
                [f"{k['label']}: {k['value']}" for k in envelope.get("kpis", [])]
                + notes
            ),
            spec=envelope["echarts"],
            data=envelope.get("data") or {"columns": [], "rows": []},
        ))
        sink(events.Done(seconds=round(time.monotonic() - started, 1)))
    finally:
        close = getattr(con, "close", None)
        if callable(close):
            close()
```

> Implementer note: drop the `widgets_tool_set` hasattr branch — it's a leftover.
> The build_tool_set call is the real path. Simplify before committing.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_chat.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/chat.py tests/test_chat.py
git commit -m "feat(chat): unified run_chat orchestrator"
```

---

### Task 2.4: `FootwearDomain`

**Files:**
- Create: `backend/footwear_domain.py`
- Test: `tests/test_footwear_domain.py`

**Interfaces:**
- Consumes: `Domain` types, `WIDGETS`, `backend.services.footwear`, `default_finalize`.
- Produces: `FootwearDomain` implementing `Domain`. `finalize` = `default_finalize(..., report_tool_names={w.tool_name for w in WIDGETS})`. `step_label` = the Spanish `_STEP_TITLES` + `_FLOW_LABEL` formatting currently in `orchestrator_footwear._step_label`. `system_prompt` / `prose_closeout_instruction` = the Spanish strings currently in `orchestrator_footwear._SYSTEM` and its close-out message. `app_config()` returns the footwear branding + the 10 example prompts + the ECharts theme list + one `TabDescriptor("reports", "Panel de reportes", "bars", "widget_grid", widgets=[...], filters=["flow","heading","months"])`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_footwear_domain.py
from backend.footwear_domain import FootwearDomain


def test_app_config_has_reports_tab_and_prompts():
    cfg = FootwearDomain().app_config()
    assert cfg.branding.name == "Analista de Calzado"
    assert len(cfg.example_prompts) == 10
    tab = cfg.tabs[0]
    assert tab.kind == "widget_grid"
    assert "evolution" in tab.widgets


def test_step_label_is_spanish():
    s = FootwearDomain().step_label("footwear_top_partners", {"flow": "IMPORT", "top_n": 5})
    assert s.label == "Calculando el ranking de países"
    assert "Importación" in s.detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_footwear_domain.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Port the Spanish constants from `orchestrator_footwear.py` (`_SYSTEM`,
`_STEP_TITLES`, `_FLOW_LABEL`, the `_step_label` body, the close-out instruction
string at line ~135) and the `app_config` data from `frontend/index.html`
(`PROMPTS` array, branding strings, `THEMES`). Use `backend.config.DATACOMEX_PATH`
for `open_connection` (read-only duckdb). `web_dir()` returns
`str(Path(__file__).parent.parent / "frontend")` for now (Phase 4 moves it).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_footwear_domain.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/footwear_domain.py tests/test_footwear_domain.py
git commit -m "feat(footwear): FootwearDomain"
```

---

### Task 2.5: `SqlDomain`

**Files:**
- Create: `backend/sql_domain.py`
- Test: `tests/test_sql_domain.py`

**Interfaces:**
- Consumes: `backend.agents.data_agent.answer_data_question`, `backend.charts`, `backend.agents.llm.structured_json`, the `_CHART_SCHEMA` currently in `backend/agents/orchestrator.py`.
- Produces: `SqlDomain` implementing `Domain`. `widgets()` = `[]`. `extra_tools()` returns the `query_data` tool (def + a handler that calls `answer_data_question`, appends to an internal `datasets` list, returns the JSON payload with the "you're done" note). `finalize(agent, con)` picks the most chartable dataset (`_chartability` argmax, latest wins), runs the `structured_json` chart-mapping call + `charts.build_option`, returns a `ChartEnvelope` (with `data` populated). `system_prompt` = the English `_SYSTEM` from `orchestrator.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sql_domain.py
from backend.sql_domain import SqlDomain


def test_widgets_empty_and_query_tool_present():
    d = SqlDomain()
    assert d.widgets() == []
    assert d.extra_tools()["defs"][0]["name"] == "query_data"


def test_finalize_builds_envelope_from_dataset(monkeypatch):
    d = SqlDomain()
    # simulate a completed query
    from backend.agents.data_agent import DataResult
    d._datasets = [DataResult(ok=True, sql="SELECT 1", columns=["region", "rev"],
                              rows=[["EMEA", 10], ["APAC", 7]], row_count=2)]
    monkeypatch.setattr(d, "_chart_mapping", lambda agent: {
        "chart_title": "Rev by region", "chart_meta": "",
        "chart_type": "bar", "chart_x": "region", "chart_y": ["rev"],
        "chart_series_by": None})
    env = d.finalize(agent=None, con=None)
    assert env["title"] == "Rev by region"
    assert env["data"]["columns"] == ["region", "rev"]
    assert env["echarts"]["series"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sql_domain.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Move `_CHART_SCHEMA`, `_chartability`, `rows_to_records` and the `_query_data`
closure logic from `orchestrator.py` into `SqlDomain` as methods. `finalize`
mirrors `orchestrator.run` lines 162–252 but returns the envelope instead of
sinking events (the sinking is `run_chat`'s job now). `open_connection()` uses
`backend.warehouse.db.connect()`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_sql_domain.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/sql_domain.py tests/test_sql_domain.py
git commit -m "feat: SqlDomain (free-SQL chat as a Domain)"
```

---

### Task 2.6: wire `app.py` to `run_chat` + delete the old orchestrators

**Files:**
- Modify: `backend/app.py`
- Delete: `backend/agents/orchestrator.py`, `backend/agents/orchestrator_footwear.py`
- Modify: `tests/test_endpoint.py`
- Delete: `tests/test_orchestrator.py`, `tests/test_orchestrator_footwear.py` (cases now covered by `test_chat.py` + `test_*_domain.py`)

**Interfaces:**
- Consumes: `run_chat`, `FootwearDomain`, `SqlDomain`.
- Produces: `backend.app.DOMAIN` (module-level, chosen by `config.CHAT_DOMAIN` for now — `"footwear"` → `FootwearDomain()`, else `SqlDomain()`), `backend.app.app`. `/api/chat` calls `run_chat(DOMAIN, req.message, sink, history=history)`.

- [ ] **Step 1: Update `tests/test_endpoint.py`**

The tests monkeypatch `app_module.orchestrator_run`. Change to monkeypatch
`app_module.run_chat` with a fake `(domain, message, sink, **kw)` signature.

Run: `python3 -m pytest tests/test_endpoint.py -q`
Expected: FAIL — `orchestrator_run` gone / signature mismatch.

- [ ] **Step 2: Rewire `app.py`**

```python
# backend/app.py — replace the orchestrator import + indirection
from backend.chat import run_chat
from backend.footwear_domain import FootwearDomain
from backend.sql_domain import SqlDomain

DOMAIN = FootwearDomain() if config.CHAT_DOMAIN == "footwear" else SqlDomain()

# in the /api/chat worker:
def worker() -> None:
    try:
        run_chat(DOMAIN, req.message, sink, history=history)
    except Exception as exc:
        q.put(events.ErrorEvent(message=str(exc)))
        q.put(events.Done(seconds=0.0))
    finally:
        q.put(_SENTINEL)
```

Delete the two orchestrator modules and their tests.

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — total count drops by the deleted orchestrator tests, rises by
the new domain/chat tests; **0 failures**. Investigate any failure before
committing.

- [ ] **Step 4: Manual smoke (local server)**

```bash
AUTH_ENABLED=false CHAT_DOMAIN=footwear DATACOMEX_PATH=backend/warehouse/footwear.duckdb \
  nohup python3 -m uvicorn backend.app:app --port 8099 > /tmp/srv.log 2>&1 & disown
```
Then in a browser at `http://localhost:8099/`, ask "¿cómo han evolucionado las
importaciones?" — expect streamed prose + a line chart + a non-empty "Datos" tab.
Kill the server (separate Bash call: `pkill -f "port 8099"`).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py tests/
git rm backend/agents/orchestrator.py backend/agents/orchestrator_footwear.py tests/test_orchestrator.py tests/test_orchestrator_footwear.py
git commit -m "refactor: /api/chat uses run_chat(DOMAIN); delete old orchestrators"
```

---

## Phase 3 — CSS Tokenization + JS Module Split

### Task 3.1: `build_app_config` + `/api/app-config` endpoint

**Files:**
- Create: `backend/app_config.py`
- Modify: `backend/app.py` (route + `_PUBLIC`)
- Test: `tests/test_app_config.py`

**Interfaces:**
- Consumes: `Domain.app_config()`, `Domain.widgets()`, `Domain.filter_options()`, `widget_descriptors`, `config.GOOGLE_CLIENT_ID`, `config.AUTH_ENABLED`.
- Produces: `build_app_config(domain, *, prefix_widgets=True) -> dict` shaped per spec §9 (`branding`, `auth`, `example_prompts`, `echarts_themes`, `tabs`, `widgets`, `filter_options`). `widgets[key].rest_path` is the full path (`report_prefix` + widget `rest_path`). Route `GET /api/app-config`. `/api/app-config` added to `_PUBLIC`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_config.py
from fastapi.testclient import TestClient
from backend import app as app_module


def test_app_config_public_and_shaped():
    client = TestClient(app_module.app)
    r = client.get("/api/app-config")           # no auth
    assert r.status_code == 200
    body = r.json()
    assert body["branding"]["name"] == "Analista de Calzado"
    assert "reports" == body["tabs"][0]["id"]
    assert body["widgets"]["evolution"]["rest_path"].endswith("/evolution")
    assert body["widgets"]["evolution"]["rest_path"].startswith("/api/v1/reports/footwear")
    assert isinstance(body["example_prompts"], list) and body["example_prompts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_app_config.py -q`
Expected: FAIL — 404 / route missing.

- [ ] **Step 3: Implement**

```python
# backend/app_config.py
from __future__ import annotations

import backend.config as config
from backend.domain import Domain
from backend.widgets import widget_descriptors


def build_app_config(domain: Domain) -> dict:
    cfg = domain.app_config()
    prefix = domain.report_prefix() or ""
    descs = widget_descriptors(domain.widgets())
    for d in descs.values():
        d["rest_path"] = prefix + d["rest_path"]

    con = domain.open_connection()
    try:
        fopts = domain.filter_options(con) if domain.report_prefix() else {}
    finally:
        close = getattr(con, "close", None)
        if callable(close):
            close()

    return {
        "branding": {
            "name": cfg.branding.name, "short_name": cfg.branding.short_name,
            "badge": cfg.branding.badge, "favicon": cfg.branding.favicon,
        },
        "auth": {"client_id": config.GOOGLE_CLIENT_ID, "enabled": config.AUTH_ENABLED},
        "example_prompts": list(cfg.example_prompts),
        "echarts_themes": list(cfg.echarts_themes),
        "tabs": [dataclass_to_dict(t) for t in cfg.tabs],
        "widgets": descs,
        "filter_options": fopts,
    }


def dataclass_to_dict(t) -> dict:
    import dataclasses
    return {k: v for k, v in dataclasses.asdict(t).items() if v is not None}
```

In `backend/app.py`: `_PUBLIC = ("/login.html", "/auth/", "/favicon", "/healthz", "/api/app-config")`
and `@app.get("/api/app-config")` returns `build_app_config(DOMAIN)`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_app_config.py tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app_config.py backend/app.py tests/test_app_config.py
git commit -m "feat: /api/app-config endpoint (public)"
```

---

### Task 3.2: tokenize the CSS

**Files:**
- Create: `frontend/chatkit.css` (all current `<style>` content, hex → tokens)
- Create: `frontend/app.css` (footwear overrides — likely just `--accent`)
- Modify: `frontend/index.html` (link the two stylesheets instead of inline `<style>`), `frontend/login.html`
- Modify: `backend/app.py` — nothing yet (StaticFiles already serves `frontend/`)
- Test: `tests/test_frontend_smoke.py` (add a check that `/chatkit.css` and `/app.css` are served and contain `--accent`)

**Interfaces:**
- Produces: `frontend/chatkit.css` defining on `:root`: `--bg`, `--surface`, `--surface-2`, `--border`, `--text`, `--text-dim`, `--accent`, `--accent-text`, `--danger`, `--danger-bg`. Every current hex literal replaced by `var(--…)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend_smoke.py
from fastapi.testclient import TestClient
from backend import app as app_module

client = TestClient(app_module.app)


def test_stylesheets_served_with_tokens():
    css = client.get("/chatkit.css")
    assert css.status_code == 200
    assert "--accent" in css.text
    assert client.get("/app.css").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_frontend_smoke.py -q`
Expected: FAIL — 404.

- [ ] **Step 3: Extract + tokenize**

Copy the entire current `<style>…</style>` body from `index.html` into
`frontend/chatkit.css`. Add the `:root { --bg:#faf9f8; --surface:#fff;
--border:rgba(0,0,0,.09); --text:#1c1b19; --text-dim:#6b6864; --accent:#3a53c9;
--accent-text:#fff; --danger:#b3261e; --danger-bg:rgba(179,38,30,.08);
--surface-2:#f2f0ec; }` block at the top. Replace every hex literal in the rules
with the matching `var(--…)`. `frontend/app.css` is `:root{ /* footwear keeps
the default accent */ }` (empty override, exists for the pattern). In
`index.html` and `login.html` replace `<style>…</style>` with
`<link rel="stylesheet" href="/chatkit.css"><link rel="stylesheet" href="/app.css">`.

- [ ] **Step 4: Run tests + visual check**

Run: `python3 -m pytest tests/test_frontend_smoke.py -q` → PASS
Start the local server (Task 2.6 Step 4 command) and confirm the page looks
identical to before (screenshot compare by eye).

- [ ] **Step 5: Commit**

```bash
git add frontend/chatkit.css frontend/app.css frontend/index.html frontend/login.html tests/test_frontend_smoke.py
git commit -m "refactor(frontend): extract + tokenize CSS"
```

---

### Task 3.3: split the inline `<script>` into `frontend/chatkit.js`

**Files:**
- Create: `frontend/chatkit.js` (ES module — the current inline script, reorganized behind exports)
- Rewrite: `frontend/index.html` (~60 lines)
- Test: `tests/test_frontend_smoke.py` (extend)

**Interfaces:**
- Produces `frontend/chatkit.js` exporting:
  - `boot(opts?)` — `async`: `fetch("/api/app-config")` + `fetch("/auth/me")` (redirect to `/login.html` on 401), render the sidebar shell + user avatar/menu + theme selector, wire tab switching from `config.tabs`, mount each tab (`widget_grid` → `mountWidgetGrid`; `custom` → the fn registered via `registerTab`), mount the chat view via `mountChat`.
  - `mountChat(el, { endpoint, prompts, storageKey })`
  - `mountWidgetGrid(el, { basePath, widgets, filters, filterOptions, theme })`
  - `registerTab(id, mountFn)`
  - `mountLogin(el)` — the GIS flow, reads `/api/app-config` for `branding` + `auth.client_id`.
  - internal helpers `mdLite`, `withTooltip`, the localStorage `store` — all currently in the inline script, moved verbatim.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_frontend_smoke.py
def test_index_is_thin_and_imports_module():
    html = client.get("/").text
    assert 'type="module"' in html
    assert "chatkit.js" in html
    assert len(html) < 4000               # the shell is thin now
    js = client.get("/chatkit.js")
    assert js.status_code == 200
    assert "export function boot" in js.text or "export async function boot" in js.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_frontend_smoke.py::test_index_is_thin_and_imports_module -q`
Expected: FAIL — `chatkit.js` missing; `index.html` still huge.

- [ ] **Step 3: Extract**

Move the entire inline `<script>` body into `frontend/chatkit.js`. Reorganize:
- The `PROMPTS`, branding strings, `REPORT_WIDGETS`, `THEMES`, filter markup — **delete** from JS; these now come from `/api/app-config`.
- Wrap the sidebar/user-panel/theme wiring in `boot()`.
- Wrap the chat-thread code (`renderThread`, `send`, `liveAgentBlock`, store) in `mountChat(el, cfg)` — `cfg.endpoint` replaces the hardcoded `/api/chat`; `cfg.storageKey` replaces `STORAGE_KEY`; `cfg.prompts` replaces `PROMPTS`.
- Wrap `loadReports`/`initReports` in `mountWidgetGrid(el, cfg)` — build the filter `<select>`/`<input>` elements from `cfg.filters` (param descriptors) instead of reading fixed ids; build each card's fetch URL from `cfg.widgets[key].rest_path` + the param-binding (`{name: currentFilterValue}`).
- `registerTab` writes to a module-level `Map`; `boot()` reads it for `kind:"custom"` tabs.

New `frontend/index.html`:

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analista de Calzado · DataComex</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/chatkit.css">
<link rel="stylesheet" href="/app.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.1/echarts.min.js"></script>
</head>
<body>
<div id="app"></div>
<script type="module">
  import { boot } from "/chatkit.js";
  boot();
</script>
</body>
</html>
```

- [ ] **Step 4: Run tests + full manual smoke**

Run: `python3 -m pytest tests/ -q` → PASS
Start the local server. Verify against the pre-refactor screenshots:
- sidebar, new chat, history, search, collapse
- user avatar + dropdown menu + logout
- theme selector switches ECharts theme
- ask a question → streamed prose + chart + Chart/Spec/Datos tabs
- "Panel de reportes" tab → filter bar (flow/heading/months) → 5 cards render, tooltips not clipped
- markdown in a reply renders (`**bold**`, `- lists`)
- reload `/login.html` (set `AUTH_ENABLED=true` with a throwaway client id) → branded

- [ ] **Step 5: Commit**

```bash
git add frontend/chatkit.js frontend/index.html frontend/login.html tests/test_frontend_smoke.py
git commit -m "refactor(frontend): chatkit.js ES module; thin project index.html"
```

---

### Task 3.4: unit-test the config → widget-grid param binding

**Files:**
- Create: `frontend/chatkit.test.mjs` (Node's built-in `node:test` — no deps)
- Create: `tests/test_frontend_js.py` (pytest wrapper that shells out to `node --test`)

**Interfaces:**
- `chatkit.js` must export (or the test imports internal) `buildWidgetUrl(widgetDesc, filterValues) -> string` and `buildFilterControls(paramDescs) -> {el, read()}` so they're unit-testable. Refactor them out of `mountWidgetGrid` if needed.

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/chatkit.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import { buildWidgetUrl } from "./chatkit.js";

test("buildWidgetUrl only includes params the widget declares", () => {
  const desc = {
    rest_path: "/api/v1/reports/footwear/product-mix",
    params: [{ name: "flow", type: "enum" }],
  };
  const url = buildWidgetUrl(desc, { flow: "IMPORT", heading: "64", months: 24 });
  assert.strictEqual(url, "/api/v1/reports/footwear/product-mix?flow=IMPORT");
});

test("buildWidgetUrl applies defaults for missing values", () => {
  const desc = {
    rest_path: "/x",
    params: [{ name: "months", type: "int", default: 24 }],
  };
  assert.strictEqual(buildWidgetUrl(desc, {}), "/x?months=24");
});
```

```python
# tests/test_frontend_js.py
import subprocess


def test_chatkit_js_units():
    r = subprocess.run(["node", "--test", "frontend/"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test frontend/`
Expected: FAIL — `buildWidgetUrl` not exported.

- [ ] **Step 3: Extract `buildWidgetUrl` / `buildFilterControls` as named exports**

Pull the URL-construction and filter-control logic out of `mountWidgetGrid` into
exported functions; `mountWidgetGrid` calls them.

- [ ] **Step 4: Run tests**

Run: `node --test frontend/ && python3 -m pytest tests/test_frontend_js.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/chatkit.js frontend/chatkit.test.mjs tests/test_frontend_js.py
git commit -m "test(frontend): unit tests for widget-grid param binding"
```

---

## Phase 4 — File Move (pure, zero behavior change)

### Task 4.1: scaffold `packages/chatkit/` + `projects/footwear/`

**Files:**
- Create: `packages/chatkit/pyproject.toml`, `packages/chatkit/chatkit/__init__.py`
- Create: `projects/footwear/pyproject.toml` (or just a package dir), `projects/footwear/__init__.py`
- Modify: repo root `pyproject.toml` / `pytest.ini` — test paths, editable install

**Interfaces:**
- Produces: `pip install -e packages/chatkit` works; `import chatkit` works.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_packaging.py  (temporary, at repo root — moves in 4.5)
def test_chatkit_importable():
    import chatkit  # noqa
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_packaging.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'chatkit'`

- [ ] **Step 3: Scaffold**

```toml
# packages/chatkit/pyproject.toml
[project]
name = "chatkit"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi", "uvicorn[standard]", "duckdb", "pydantic",
  "anthropic", "openai", "google-auth", "requests", "itsdangerous",
]

[project.optional-dependencies]
sql = []   # data_agent needs nothing extra today; placeholder

[tool.setuptools.packages.find]
where = ["."]
include = ["chatkit*"]

[tool.setuptools.package-data]
chatkit = ["frontend/*"]
```

```bash
mkdir -p packages/chatkit/chatkit projects/footwear
touch packages/chatkit/chatkit/__init__.py projects/footwear/__init__.py
pip install -e packages/chatkit
```

- [ ] **Step 4: Run test**

Run: `python3 -m pytest tests/test_packaging.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/ projects/ tests/test_packaging.py pyproject.toml
git commit -m "chore: scaffold packages/chatkit + projects/footwear"
```

---

### Task 4.2: move core modules into `chatkit/`

**Files:** (git mv, then fix imports)
- `backend/events.py` → `packages/chatkit/chatkit/events.py`
- `backend/history.py` → `chatkit/history.py`
- `backend/charts.py` → `chatkit/charts.py`
- `backend/widgets.py` → `chatkit/widgets.py`
- `backend/domain.py` → `chatkit/domain.py`
- `backend/chat.py` → `chatkit/chat.py`
- `backend/app_config.py` → `chatkit/app_config.py`
- `backend/auth.py` → `chatkit/auth/google.py`
- `backend/auth_db.py` → `chatkit/auth/db.py`
- `backend/routers/auth.py` → `chatkit/auth/router.py`
- `backend/agents/llm.py` → `chatkit/agents/llm.py`
- `backend/agents/data_agent.py` → `chatkit/sql_domain/data_agent.py`
- `backend/warehouse/db.py` → `chatkit/warehouse/duckdb.py`
- `backend/sql_domain.py` → `chatkit/sql_domain/__init__.py` (merge)
- `backend/app.py` → `chatkit/app.py` (becomes `create_app` — Task 4.4)

**Interfaces:**
- All `from backend.X` inside moved files become `from chatkit.X`.
- Produces: `chatkit.events`, `chatkit.history`, `chatkit.charts`, `chatkit.widgets`, `chatkit.domain`, `chatkit.chat`, `chatkit.agents.llm`, `chatkit.auth.google`, `chatkit.auth.db`, `chatkit.auth.router`, `chatkit.warehouse.duckdb`, `chatkit.sql_domain.SqlDomain`.

- [ ] **Step 1: `git mv` the files** (one commit per logical group is fine; keep the tree compiling between groups is not required until Step 3)

- [ ] **Step 2: Fix imports** — global find/replace `from backend\.` → `from chatkit.` **within moved files only**. `backend/config.py` is NOT moved yet (Task 4.3 handles Settings); moved files that import `backend.config` temporarily import `from chatkit._compat import config` — a 1-line shim `import backend.config as config` — removed in 4.3.

- [ ] **Step 3: Run the full suite** (tests still under `tests/`, still importing `backend.*` for footwear code)

Run: `python3 -m pytest tests/ -q`
Expected: PASS — the footwear code still imports the moved modules via a
`backend/__init__.py` re-export shim added here:
`backend/events.py` etc. become `from chatkit.events import *`. Add these shims
so `tests/` and `backend/footwear_domain.py` keep working during the move.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move core modules into chatkit package (with backend shims)"
```

---

### Task 4.3: `Settings` object; retire module-level `config` in core

**Files:**
- Create: `chatkit/settings.py`
- Modify: every `chatkit/*` module that read `backend.config` / `chatkit._compat.config`
- Modify: `chatkit/agents/llm.py` — `get_client(settings)`, drop `_client` global + `reset_client`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `chatkit.settings.Settings` frozen dataclass with `from_env() -> Settings`; fields per spec §10/§11. `auth_db_path` has **no default** (raises if unset when `auth_enabled`). `create_app` builds one and threads it: `run_chat(domain, ..., settings)`, `llm.run_agent(..., client=settings_client)`, `warehouse.duckdb.connect(path, max_rows=settings.sql_max_rows, timeout=settings.sql_timeout_s)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings.py
import pytest
from chatkit.settings import Settings


def test_from_env_reads_llm_and_auth(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DB_PATH", "/tmp/x.sqlite")
    s = Settings.from_env()
    assert s.llm_provider == "deepseek"
    assert s.auth_enabled is True
    assert str(s.auth_db_path) == "/tmp/x.sqlite"


def test_auth_db_path_required_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("AUTH_DB_PATH", raising=False)
    with pytest.raises(ValueError):
        Settings.from_env()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_settings.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `Settings` + thread it**

Build `Settings` from the current `backend/config.py` field-by-field (LLM + auth +
SQL groups only). `create_app` calls `Settings.from_env()`. Update `llm.py` to
accept a client/settings; delete `_client`/`reset_client` and update
`tests/test_llm*.py` to pass a fake client. Remove the `chatkit._compat` shim.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chatkit/ tests/
git commit -m "feat(chatkit): Settings object; drop module-global LLM client"
```

---

### Task 4.4: `create_app(domain)` factory

**Files:**
- Modify: `chatkit/app.py` — export `create_app`
- Create: `chatkit/__init__.py` — `from chatkit.app import create_app; from chatkit.domain import Domain; from chatkit.widgets import Widget, Param`
- Test: `tests/test_create_app.py`

**Interfaces:**
- Produces: `create_app(domain: Domain, *, settings: Settings | None = None) -> FastAPI` per spec §10. Mount order: auth router → generated widget router (`build_rest_router(domain.widgets(), prefix=domain.report_prefix(), con_factory=domain.open_connection)`) → `/api/app-config`, `/api/chat`, `/healthz` → `/_chatkit` static (package `frontend/`) → `/` static (`domain.web_dir()`, html=True), **last**.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_create_app.py
from fastapi.testclient import TestClient
from chatkit import create_app
from chatkit._demo.domain import DemoDomain


def test_create_app_serves_config_chat_and_static():
    app = create_app(DemoDomain())
    c = TestClient(app)
    assert c.get("/healthz").json() == {"ok": True}
    assert c.get("/api/app-config").status_code == 200
    assert c.get("/_chatkit/chatkit.js").status_code == 200
    assert c.get("/").status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_create_app.py -q`
Expected: FAIL — `create_app` / `DemoDomain` missing (DemoDomain is Task 4.5 — write that first if executing strictly; the two tasks may be done together).

- [ ] **Step 3: Implement `create_app`**

Port `backend/app.py`'s body into a factory. `auth_gate` becomes an inner
function closed over `settings`. Session middleware `https_only=settings.auth_enabled`.
`/api/chat` worker calls `run_chat(domain, req.message, sink, history=history, settings=settings)`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_create_app.py tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chatkit/ tests/test_create_app.py
git commit -m "feat(chatkit): create_app(domain) factory"
```

---

### Task 4.5: `chatkit._demo` fixture domain

**Files:**
- `backend/warehouse/schema.py` → `chatkit/_demo/schema.py` (keep `introspect`; `SCHEMA_NOTES` stays here)
- `backend/warehouse/seed.py` → `chatkit/_demo/seed.py`
- Create: `chatkit/_demo/domain.py` — `DemoDomain` (a `SqlDomain` subclass or a 2-widget domain over the demo warehouse), `web_dir()` → a tiny `chatkit/_demo/web/` with a minimal `index.html`
- Test: `tests/test_demo_domain.py`

**Interfaces:**
- Produces: `chatkit._demo.domain.DemoDomain` — used by all `chatkit` tests so they never import `projects.*`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_demo_domain.py
from chatkit._demo.domain import DemoDomain


def test_demo_domain_is_usable():
    d = DemoDomain()
    cfg = d.app_config()
    assert cfg.branding.name
    assert isinstance(d.widgets(), list)
```

- [ ] **Step 2: Run to verify it fails** — module missing.

- [ ] **Step 3: Implement** — move the two files; write `DemoDomain` as the
  smallest thing satisfying `Domain` (reuse `SqlDomain` for chat; `widgets()` can
  be `[]` or two toy widgets over the seed warehouse; `web_dir()` returns a dir
  with a 20-line `index.html` importing `/_chatkit/chatkit.js`).

- [ ] **Step 4: Run the full suite** → PASS

- [ ] **Step 5: Commit**

```bash
git add chatkit/_demo/ tests/test_demo_domain.py
git commit -m "feat(chatkit): _demo fixture domain (was the analytics demo warehouse)"
```

---

### Task 4.6: move footwear code into `projects/footwear/`

**Files:** (git mv + import fixes)
- `backend/footwear_domain.py` → `projects/footwear/domain.py`
- `backend/services/footwear.py` → `projects/footwear/services/footwear.py`
- `backend/services/footwear_widgets.py` → `projects/footwear/services/widgets.py`
- `backend/warehouse/datacomex_schema.py` → `projects/footwear/warehouse/schema.py`
- `backend/warehouse/datacomex_seed.py` → `projects/footwear/warehouse/seed.py`
- `backend/ingest/` → `projects/footwear/ingest/`
- `backend/config.py` → `projects/footwear/config.py` (only `DATACOMEX_PATH`, `DATA_COMEX_TOKEN` remain; the rest moved to `Settings`)
- `frontend/*` → `projects/footwear/web/*` (`chatkit.js`/`chatkit.css` do NOT move — they're already in `chatkit/frontend/`; `index.html`, `login.html`, `app.css` move)
- Create: `projects/footwear/main.py` — `from chatkit import create_app; from projects.footwear.domain import FootwearDomain; app = create_app(FootwearDomain())`
- Delete: `backend/` entirely (all shims removed), `backend/app.py`

**Interfaces:**
- Produces: `projects.footwear.main.app` — the deployable ASGI app.

- [ ] **Step 1:** move `chatkit.js`/`chatkit.css` (created in Phase 3 under `frontend/`) into `packages/chatkit/chatkit/frontend/`. Update `create_app`'s static mount to `importlib.resources`-locate them.

- [ ] **Step 2:** `git mv` the footwear files per the list. Fix imports (`from backend.services.footwear` → `from projects.footwear.services.footwear`, etc.).

- [ ] **Step 3:** delete `backend/`. Update `FootwearDomain.web_dir()` → `str(Path(__file__).parent / "web")`.

- [ ] **Step 4: Run the full suite** (tests still at repo `tests/` — split in 4.7)

Run: `python3 -m pytest tests/ -q`
Expected: PASS — fix every import error before proceeding. This is the riskiest
task; go file-by-file.

- [ ] **Step 5: Manual smoke**

```bash
AUTH_ENABLED=false DATACOMEX_PATH=projects/footwear/warehouse/footwear.duckdb \
  nohup python3 -m uvicorn projects.footwear.main:app --port 8099 > /tmp/srv.log 2>&1 & disown
```
Full walkthrough (chat, reports tab, themes, login page). Kill server (separate call).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move footwear code into projects/footwear; delete backend/"
```

---

### Task 4.7: split test suites + CI dependency-direction check + drop committed data files

**Files:**
- Move `tests/test_{footwear,footwear_widgets,footwear_domain,tools_footwear,reports_endpoint,datacomex_seed,ingest_*}.py` → `projects/footwear/tests/`
- Move the rest → `packages/chatkit/tests/`
- `tests/test_chat.py`, `test_sql_domain.py`, `test_domain.py`, `test_widgets.py`, `test_create_app.py`, `test_app_config.py`, `test_demo_domain.py`, `test_settings.py`, `test_history.py`, `test_charts.py`, `test_events.py`, `test_llm*.py`, `test_auth*.py`, `test_warehouse_db.py`, `test_frontend_smoke.py`, `test_frontend_js.py` → `packages/chatkit/tests/`
- `test_config.py` → split: LLM/auth parts to chatkit, `DATACOMEX_*` parts to footwear
- Create: `Makefile` target `check-deps`
- Modify: root `pyproject.toml` / add `pytest.ini` with `testpaths = packages/chatkit/tests projects/footwear/tests`
- Delete from git: `backend/warehouse/auth.sqlite`, `backend/warehouse/footwear.duckdb`, `backend/warehouse/warehouse.duckdb` (already gone with `backend/` in 4.6 — confirm they were `git rm`'d, not just deleted)

- [ ] **Step 1:** `git mv` the test files. Fix imports in each (`backend.` → `chatkit.` or `projects.footwear.`).

- [ ] **Step 2:** the dep-direction check:

```makefile
# Makefile
check-deps:
	@! git grep -nE "^(from|import) projects" -- 'packages/chatkit/**/*.py' \
	  || (echo "chatkit must not import projects.*" && exit 1)
	@echo "dependency direction OK"
```

- [ ] **Step 3:** `.gitignore` — ensure `*.duckdb`, `*.sqlite` under both trees are
  ignored. Confirm `git ls-files | grep -E '\.(duckdb|sqlite)$'` is empty.

- [ ] **Step 4: Run everything**

```bash
python3 -m pytest packages/chatkit/tests projects/footwear/tests -q
make check-deps
node --test packages/chatkit/chatkit/frontend/
```
Expected: all green; `chatkit` suite passes **without** `projects/` importable
(verify: `cd packages/chatkit && python3 -m pytest tests -q`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: split test suites; CI dep-direction check; drop committed data files"
```

---

### Task 4.8: update `Dockerfile` + compose for the new layout

**Files:**
- Modify: `Dockerfile` (or create `projects/footwear/Dockerfile`)
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Produces: an image that `pip install ./packages/chatkit`, copies `projects/footwear/`, runs `uvicorn projects.footwear.main:app --proxy-headers --forwarded-allow-ips '*'`.

- [ ] **Step 1:** rewrite the Dockerfile:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY packages/chatkit ./packages/chatkit
RUN pip install --no-cache-dir ./packages/chatkit
COPY projects/footwear ./projects/footwear
COPY pyproject.toml .
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "projects.footwear.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

- [ ] **Step 2:** `docker build -t footwear-test .` → succeeds.

- [ ] **Step 3:** `docker run --rm -e AUTH_ENABLED=false -e DATACOMEX_PATH=/app/projects/footwear/warehouse/footwear.duckdb -p 8100:8000 footwear-test` — hit `http://localhost:8100/healthz` and `/api/app-config`.

- [ ] **Step 4:** update `README.md` — new layout, `pip install -e packages/chatkit`, how to run tests (both suites), how to start a new project.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml README.md
git commit -m "chore: Dockerfile + docs for monorepo layout"
```

---

### Task 4.9: final full-suite + deploy dry-run + push

- [ ] **Step 1:** `python3 -m pytest packages/chatkit/tests projects/footwear/tests -q` → 0 failures.
- [ ] **Step 2:** `make check-deps` → OK.
- [ ] **Step 3:** `cd packages/chatkit && python3 -m pytest tests -q` (isolation check) → OK.
- [ ] **Step 4:** local server smoke on `projects.footwear.main:app` — full walkthrough one more time against the Phase 3 checklist.
- [ ] **Step 5:** push the branch.

```bash
git push -u origin chatkit-extraction
```

Do **not** merge to `Calzados` or `main` — that's a separate reviewed step, and
Dokploy auto-deploys `Calzados`. Open the PR for review.

---

## Self-Review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §3.1 core layout | 4.2, 4.4, 4.5 |
| §3.2 project layout | 4.1, 4.6 |
| §3.3 dividing rule | enforced by 4.7 `check-deps` |
| §4 `Domain` contract | 2.2 (protocol), 2.4 (`FootwearDomain`), 2.5 (`SqlDomain`), 4.5 (`DemoDomain`) |
| §5 `Widget` single declaration | 1.1–1.6 |
| §6 report tabs (`widget_grid` / `custom`) | 2.4 (`TabDescriptor` data), 3.3 (`boot` renders them, `registerTab`) |
| §7 envelope (`notes`, `data`, `chart_type` helper) | 1.5 (`notes`), 2.3 (`data` always set), 1.1 (`chart_type_param`) |
| §8 `chatkit.js` API | 3.3, 3.4 |
| §9 `/api/app-config` shape | 3.1 |
| §10 `create_app` + `Settings` | 4.3, 4.4 |
| §11 config split | 4.3, 4.6 |
| §12 monorepo + CI check | 4.1, 4.7 |
| §13 migration order | phase order matches Steps 1→4; Steps 5–6 out of scope (stated) |
| §14 test strategy | 4.5 (fixture domain), 4.7 (suite split + isolation check), 3.4 (frontend unit) |
| §15 risk 1 (`chatkit.js` API) | mitigated: 3.3 builds it in-repo before the move |
| §15 risk 2 (`finalize` leak) | 2.3+2.4+2.5 land together, same suite |
| §15 risk 3 (globals) | 4.3 |
| §15 risk 4 (`AUTH_DB_PATH` / data files) | 4.3 (required), 4.7 (`git rm`) |
| §15 risk 6 (no frontend tests) | 3.2, 3.3, 3.4 add smoke + unit |
| §16 out of scope | respected — no server-side history, no npm publish, no generator |

**Placeholder scan:** the `SqlDomain.finalize` and `FootwearDomain` tasks
reference "port the logic from `orchestrator*.py` lines X–Y" rather than
reprinting ~90 lines each — acceptable because the source is in git and the task
names the exact function and behavior; the *tests* are concrete. `_demo`
`DemoDomain` widget count is left as "`[]` or two toy widgets" — implementer's
call, both satisfy the contract. No `TODO`/`TBD`/"add error handling".

**Type consistency:** `ChartEnvelope` is a dict everywhere (not a class) — spec
§7 shows `TypedDict`; plan uses plain dicts for simplicity, consistent across
1.5/2.2/2.3. `default_finalize` signature: `(agent, con, *, report_tool_names)`
in 2.2 — `FootwearDomain` in 2.4 calls it with that kwarg. `run_chat` signature
gains `settings=` only in 4.3/4.4 (Phase 2 version has no `settings` param;
Phase 4 adds it) — noted in 4.4 Step 3. `build_tool_set(widgets, con)` positional
in 1.4, called the same way in 2.3 and 1.6.

**Gaps found & fixed inline:** none requiring new tasks. One note: Phase 2's
`run_chat` uses `config.LLM_MODEL` directly; Phase 4 Task 4.3 must route that
through `Settings` — added an explicit line to 4.3 Step 3.
