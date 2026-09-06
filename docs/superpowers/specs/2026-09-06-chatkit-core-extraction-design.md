# chatkit — reusable core extraction

**Status:** design approved in chat, spec under review
**Date:** 2026-09-06
**Branch of work:** `Calzados` (footwear app is the reference implementation)

## 1. Goal

Extract the reusable parts of "Analista de Calzado" into an installable core
package (`chatkit`, pip, semver) so that new projects — *chat + Google login +
a data domain + a few report tabs* — are a thin repo that implements only their
domain. The footwear app becomes the first consumer and the reference
implementation.

Non-goal: a general-purpose UI framework. `chatkit` is opinionated about the
shape of the app (left sidebar chat history, a chat thread with streamed prose +
one ECharts chart per answer, optional report tabs with a filter bar + a widget
grid). Projects that need a fundamentally different shape fork.

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| Reuse mechanism | Installable core package + thin project repo | Central fixes propagate; projects stay small |
| Frontend ownership | **Project owns `index.html` / `login.html` / `app.css`**; core ships `chatkit.js` (ES module, no build step) + tokenized `chatkit.css` | A JSON-configured monolithic HTML forces a fork the first time a project needs a non-grid tab (map, data table, upload form). A JS module API does not. |
| Widget declaration | One `Widget(...)` descriptor per report; core derives the REST route, the chat tool def, the tool handler and the frontend descriptor from it | Today each widget is declared twice (REST + tool) and they have already diverged (`taric` vs `heading`) |
| Chat orchestrator | One unified `run_chat(domain, ...)` with a pluggable `finalize()` step | `orchestrator.py` and `orchestrator_footwear.py` are the same control flow; keeping both guarantees drift (already dead "Datos" tab in footwear mode) |
| Free-SQL mode | Shipped as a prebuilt `SqlDomain` in core (optional extra deps), not a parallel orchestrator | Same optionality, half the control flow |
| Repo topology | Monorepo now: `packages/chatkit/` + `projects/footwear/`. Extract `chatkit` to its own repo on *"3rd project OR first version skew"* | One consumer today; a second repo buys nothing and costs a release cycle per change |
| Dependency direction | CI check: nothing under `packages/chatkit/**` imports `projects.*`. `pip install -e packages/chatkit` from day one | Exercise the packaging continuously |
| Migration order | In-place refactors first (widget unification → orchestrator unification → CSS/JS split), then a behavior-free file move, then project #2 | Don't move code to make it reusable before "reusable" is defined |
| `is_provisional` in the envelope | Replaced by generic `meta.notes: list[str]` rendered verbatim | It is a DataComex concept hardcoded in 3 places |
| Package config defaults | A `Settings` object built in `create_app`; no package-relative default for `AUTH_DB_PATH` | Module-level config + a committed `auth.sqlite` breaks once pip-installed into site-packages |

## 3. Architecture: core vs project

### 3.1 `packages/chatkit/` (the package)

```
chatkit/
  __init__.py            # exports: create_app, Domain, Widget, ChartEnvelope, run_chat
  app.py                 # create_app(domain) -> FastAPI  (factory)
  settings.py            # Settings dataclass; from_env(); passed down explicitly
  events.py              # SSE event contract (unchanged)
  history.py             # clean_history, MAX_HISTORY_TURNS  (moved out of the SQL path)
  chat.py                # run_chat(domain, message, sink, history, settings)  — unified orchestrator
  charts.py              # deterministic ECharts option builder (unchanged)
  auth/
    __init__.py
    google.py            # verify_google_token, is_allowed          (was backend/auth.py)
    db.py                # users / session_log SQLite                (was backend/auth_db.py)
    router.py            # /auth/*                                   (was backend/routers/auth.py)
  agents/
    llm.py               # provider abstraction (unchanged API; client built from Settings)
  warehouse/
    duckdb.py            # read_only_connection(path, *, max_rows, timeout) — generic
  sql_domain/            # OPTIONAL extra: chatkit[sql]
    __init__.py          # SqlDomain(warehouse_path, schema_notes)
    data_agent.py        # NL question -> SQL -> rows                 (was backend/agents/data_agent.py)
    schema.py            # introspect(con)                           (was backend/warehouse/schema.py, minus SCHEMA_NOTES)
  frontend/
    chatkit.js           # ES module: mountChat, mountWidgetGrid, registerTab, mountLogin
    chatkit.css          # tokenized: --bg, --surface, --accent, --danger, --text, ...
  _demo/                 # core's own fixture domain for tests (NOT shipped as a public API)
    domain.py            # 2-widget demo domain
    seed.py + schema.py  # the current demo warehouse (was backend/warehouse/seed.py + schema.py SCHEMA_NOTES)
```

### 3.2 `projects/footwear/` (the thin project)

```
projects/footwear/
  main.py                # app = create_app(FootwearDomain(settings))
  domain.py              # FootwearDomain implements Domain
  config.py              # DATACOMEX_PATH, DATA_COMEX_TOKEN  (project settings only)
  services/
    footwear.py          # domain SQL + ChartEnvelope builders   (unchanged logic)
  warehouse/
    schema.py            # datacomex schema DDL                  (was datacomex_schema.py)
    seed.py              # synthetic seed                        (was datacomex_seed.py)
  ingest/                # real DataComex pipeline               (unchanged)
  web/
    index.html           # ~60 lines: imports chatkit.js, declares tabs
    login.html           # ~30 lines: imports mountLogin
    app.css              # brand token overrides + any project-specific rules
  Dockerfile             # pip install chatkit==X.Y.Z ; copy project
  tests/                 # footwear-specific tests only
```

### 3.3 The dividing rule

A file that mentions *calzado / TARIC / DataComex / 6401* belongs to the project.
A file that is chat / auth / chart / SSE infrastructure belongs to core. The
**demo** warehouse (`SCHEMA_NOTES`, `seed.py`) is a third category: it is core's
private test fixture, not a public part of `chatkit` and not footwear.

## 4. The `Domain` contract

A project supplies one `Domain` instance to `create_app`. It is a small object
with attributes and a few methods — not a large Protocol.

```python
@dataclass
class Branding:
    name: str                 # "Analista de Calzado"
    short_name: str            # sidebar: "Calzado · DataComex"
    badge: str                 # header pill: "DataComex · TARIC 64"
    favicon: str               # emoji or path
    # colors live in the project's app.css as token overrides, not here

@dataclass
class AppConfig:
    branding: Branding
    example_prompts: list[str]
    echarts_themes: list[str]  # theme ids the selector exposes; "lumen" ships in chatkit.js
    tabs: list[TabDescriptor]  # report tabs; see §6

class Domain(Protocol):
    settings: object                      # project settings object (opaque to core)

    # ---- identity / UI -------------------------------------------------
    def app_config(self) -> AppConfig: ...

    # ---- chat --------------------------------------------------------
    system_prompt: str
    prose_closeout_instruction: str       # domain-supplied, localized
                                          # ("Resume el hallazgo en 1-3 frases…")

    def open_connection(self): ...        # -> a read-only DB connection, or None
    def widgets(self) -> list[Widget]: ...  # §5 — also the source of the chat tools

    def extra_tools(self) -> ToolSet | None: ...   # non-widget tools
                                                   # (e.g. resolve_footwear_product).
        # ToolSet = {"defs": list[dict], "handlers": dict[str, Callable[..., str]]}

    def web_dir(self) -> str: ...          # path to the project's web/ (index.html, login.html, app.css)

    def finalize(self, agent: AgentResult, con) -> ChartEnvelope | None: ...
        # how to turn the agent's tool calls into the chart to show.
        # default impl: last successful widget tool's envelope.
        # SqlDomain overrides this with the structured_json + charts.build_option path.

    def step_label(self, name: str, tool_input: dict) -> Step | None: ...
        # optional; default renders "name · k=v · k=v"

    # ---- reports (optional) ----------------------------------------
    def report_prefix(self) -> str: ...   # "/api/v1/reports/footwear"
    def filter_options(self, con) -> dict: ...  # feeds dynamic filter selects
```

`SqlDomain` (in `chatkit.sql_domain`) is a concrete `Domain` implementing
free-SQL chat: `widgets()` returns `[]`, `extra_tools()` returns the `query_data`
tool, `finalize()` runs the `structured_json` chart-mapping call and
`charts.build_option`.

## 5. The `Widget` descriptor — declare once

```python
@dataclass
class Param:
    name: str                      # "flow"
    type: Literal["enum", "int", "str", "period"]
    required: bool = False
    default: Any = None
    enum: list[str] | None = None  # for type="enum"
    # for the frontend filter bar:
    ui_label: str | None = None    # "Flujo"; None => not shown as a filter
    ui_options: list[dict] | None = None          # static [{value,label}]
    ui_options_from: str | None = None            # key into filter_options(con)
    ui_option_label: str | None = None            # "{code} — {description}"

@dataclass
class Widget:
    key: str                       # "evolution" — stable id
    fn: Callable[..., ChartEnvelope]  # services.footwear.evolution
    params: list[Param]
    # REST
    rest_path: str                 # "/evolution" (appended to report_prefix)
    # chat tool
    tool_name: str                 # "footwear_market_overview"
    tool_description: str          # localized
    chart_types: list[str] | None = None  # exposes a chart_type enum param to the LLM
    # frontend grid
    span: Literal["full", "half"] = "full"
    in_grid: bool = True           # some widgets are chat-only
```

From one `Widget`, `create_app` generates:

1. **REST route** `GET {report_prefix}{rest_path}` — query params from `params`,
   calls `fn(con, **kwargs)`, returns the `ChartEnvelope`.
2. **Chat tool def** — `tool_name` + an `input_schema` built from `params`
   (+ a `chart_type` enum if `chart_types` is set).
3. **Chat tool handler** — `lambda **kw: json.dumps(fn(con, **kw))`.
4. **Frontend widget descriptor** in `/api/app-config` — `{key, rest_path,
   params: [...], span}` so `mountWidgetGrid` knows how to call it.

This removes `backend/routers/reports.py` (generated) and the hand-written tool
defs/handlers in `backend/agents/tools_footwear.py` (generated). The domain keeps
only `services/footwear.py` (the actual SQL) and the `Widget` list.

**Param naming is unified** at the descriptor: `heading` everywhere (drop the
REST-only `taric` alias).

## 6. Report tabs

```python
@dataclass
class TabDescriptor:
    id: str                        # "reports"
    label: str                     # "Panel de reportes"
    icon: str                      # a chatkit.js built-in icon id, or an SVG string
    kind: Literal["widget_grid", "custom"]
    # kind="widget_grid": rendered by chatkit.js from the widget descriptors
    widgets: list[str] | None = None       # widget keys, in order; None => all in_grid
    filters: list[str] | None = None       # param names to show in the filter bar
    # kind="custom": the project's index.html registers a mount fn under this id
```

`kind="widget_grid"` covers today's reports panel entirely from config.
`kind="custom"` is the escape hatch: `/api/app-config` lists the tab, the
project's `index.html` calls `registerTab("scenario", el => { ... })` with
arbitrary code. **No JSON schema ever has to express a non-grid tab.**

## 7. Chart envelope contract

```python
class ChartEnvelope(TypedDict):
    widget: str                    # stable id
    title: str                     # pre-localized (i18n is the domain's job)
    echarts: dict                  # a valid option with NO colors (theme owns color)
    kpis: list[Kpi]                # values pre-formatted strings
    meta: Meta
    data: NotRequired[DataTable]   # {columns: [...], rows: [[...]]} — optional

class Kpi(TypedDict):
    label: str
    value: str                     # "+12.4%", "80.0%", "-1.2 M€"
    tone: Literal["positive", "negative", "neutral"]

class Meta(TypedDict):
    unit: NotRequired[str]         # "EUR", "EUR/kg"
    granularity: NotRequired[str]  # "monthly", "range"
    notes: NotRequired[list[str]]  # ["incluye datos provisionales", ...] — rendered verbatim
```

Changes vs today:
- `meta.is_provisional: bool` → `meta.notes: list[str]`. `services/footwear.py`,
  the (deleted) `orchestrator_footwear._meta_line`, and the frontend all update.
- `data` becomes a real optional field. The unified orchestrator always populates
  it (from the widget's rows, or from the SQL result), so the chat "Datos" tab
  works in every mode.
- `_chart_type_field` (the "ask the LLM to re-render as bars" helper) moves to a
  core helper `chatkit.widgets.chart_type_param(chart_types)`.

## 8. `chatkit.js` — the frontend module API

Served by the package at `/_chatkit/chatkit.js` and `/_chatkit/chatkit.css`.
No build step: the project's `index.html` uses `<script type="module">`.

```js
import {
  mountChat, mountWidgetGrid, registerTab, mountLogin, boot
} from "/_chatkit/chatkit.js";

// boot() fetches /api/app-config and /auth/me, wires the sidebar + user panel +
// theme selector + tab switching, then calls the mount fns for each tab.
boot({
  // custom tabs register their mount fn before boot()
});

registerTab("scenario", (el, ctx) => {
  // ctx: { apiFetch, theme, onThemeChange }
  el.innerHTML = "...";
});
```

| Export | Responsibility |
|---|---|
| `boot(opts)` | Auth gate, fetch `/api/app-config`, render shell (sidebar, chat-history store, user avatar+menu, theme selector), mount tabs |
| `mountChat(el, cfg)` | The chat thread: SSE to `cfg.endpoint`, streamed prose (markdown), one ECharts chart per answer, Chart/Spec/Datos tabs, localStorage store keyed by `cfg.storageKey` |
| `mountWidgetGrid(el, cfg)` | Filter bar from `cfg.filters` + card grid from `cfg.widgets`; each card fetches its `ChartEnvelope` and renders KPIs + ECharts (with the `appendToBody` tooltip fix) + `meta.notes` |
| `registerTab(id, fn)` | Register a `kind="custom"` tab's mount fn |
| `mountLogin(el, cfg)` | The GIS button flow, for the project's `login.html` |

Everything project-specific the shell needs (brand strings, prompts, themes,
tabs, widget descriptors) comes from `/api/app-config`. `chatkit.css` defines the
`lumen` look via CSS custom properties on `:root`; the project's `app.css`
overrides `--accent` etc. and adds rules for its custom tabs.

`STORAGE_KEY` becomes `chatkit:{branding.short_name}:v1` so two apps on one origin
don't share history.

## 9. `/api/app-config`

```jsonc
{
  "branding": { "name": "...", "short_name": "...", "badge": "...", "favicon": "🥾" },
  "auth": { "client_id": "...", "enabled": true },   // merged in from /auth/config
  "example_prompts": ["...", "..."],
  "echarts_themes": ["lumen", "default", "macarons", "..."],
  "tabs": [
    { "id": "reports", "label": "Panel de reportes", "icon": "bars",
      "kind": "widget_grid",
      "widgets": ["evolution", "countries", "mix", "price", "balance"],
      "filters": ["flow", "heading", "months"] }
  ],
  "widgets": {
    "evolution": {
      "rest_path": "/api/v1/reports/footwear/evolution",
      "span": "full",
      "params": [
        { "name": "flow", "type": "enum", "enum": ["IMPORT","EXPORT"],
          "required": true, "default": "IMPORT",
          "ui_label": "Flujo",
          "ui_options": [{"value":"IMPORT","label":"Importaciones"},
                         {"value":"EXPORT","label":"Exportaciones"}] },
        { "name": "heading", "type": "str", "default": "64",
          "ui_label": "Partida", "ui_options_from": "headings",
          "ui_option_label": "{code} — {description}" },
        { "name": "months", "type": "int", "default": 24, "ui_label": "Meses" }
      ]
    }
  },
  "filter_options": { "headings": [ { "code": "6403", "description": "..." } ] }
}
```

`/api/app-config` **must be in `_PUBLIC`** in the auth gate (the login page reads
`branding` before the user is authenticated).

## 10. `create_app` factory + Settings

```python
def create_app(domain: Domain, *, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title=domain.app_config().branding.name)

    app.include_router(auth.router(settings))
    for route in generate_widget_routes(domain):      # §5
        app.include_router(route)
    if domain.report_prefix():
        app.add_api_route(f"{domain.report_prefix()}/filters/options",
                          lambda: domain.filter_options(domain.open_connection()))

    app.add_api_route("/api/app-config", lambda: build_app_config(domain, settings))
    app.add_api_route("/api/chat", make_chat_endpoint(domain, settings), methods=["POST"])
    app.add_api_route("/healthz", lambda: {"ok": True})

    _install_auth_gate(app, settings)                  # @middleware, before SessionMiddleware
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, ...)

    app.mount("/_chatkit", StaticFiles(directory=chatkit_frontend_dir()))
    app.mount("/", StaticFiles(directory=domain.web_dir(), html=True))  # project's index.html — LAST
    return app
```

- `Settings` is a frozen dataclass: `llm_provider`, `llm_model`, api keys,
  `reasoning_effort`, `auth_enabled`, `google_client_id`, `session_secret`,
  `session_max_age`, `allowed_emails`, `auth_db_path` (**required, no default**),
  `sql_max_rows`, `sql_timeout_s`, `max_agent_iters`.
- `llm.get_client()` takes the settings (or a client is built in `create_app` and
  threaded through). The module-global `_client` memo + `reset_client()` go away;
  tests pass a fake client via the domain/settings.
- Mount order: auth → generated widget routes → app-config/chat/healthz → static.
  Static at `/` is always last so it never shadows the API.

## 11. Config split

| Setting | Home |
|---|---|
| `LLM_*`, `*_API_KEY`, `LLM_REASONING_EFFORT`, `MAX_AGENT_ITERS`, `MAX_TOKENS` | `chatkit.Settings` |
| `AUTH_ENABLED`, `GOOGLE_CLIENT_ID`, `SESSION_SECRET`, `SESSION_MAX_AGE`, `ALLOWED_EMAILS`, `AUTH_DB_PATH` | `chatkit.Settings` |
| `SQL_MAX_ROWS`, `SQL_TIMEOUT_S` | `chatkit.Settings` (used by `warehouse/duckdb.py` and `sql_domain`) |
| `CHAT_DOMAIN` | **deleted** — the domain is chosen by which `create_app(...)` the project calls |
| `DATACOMEX_PATH`, `DATA_COMEX_TOKEN` | `projects/footwear/config.py` |
| `WAREHOUSE_PATH` | `chatkit._demo` (test fixture) / a project that uses `SqlDomain` |
| `RANDOM_SEED` | `projects/footwear` (seed script) |

`warehouse/duckdb.py` no longer imports `WAREHOUSE_PATH` at module load; the path
is always an explicit argument.

## 12. Repo topology & CI

- Monorepo. `packages/chatkit/` (with its own `pyproject.toml`, installed
  `-e`), `projects/footwear/`.
- `pytest` runs both suites; `chatkit`'s suite uses `chatkit._demo`, never
  `projects.*`.
- CI gate: `! git grep -n "import projects\|from projects" -- packages/chatkit`
  (or import-linter). Fails the build on a wrong-direction import.
- Extraction trigger (revisit topology): **3rd project OR the first time a
  consumer needs a `chatkit` version footwear isn't ready to move to.**

## 13. Migration plan (ordered)

Each step keeps the full test suite green and is independently valuable.

**Step 0 — freeze.** No new frontend features until Step 4 lands.

**Step 1 — single widget declaration (in `backend/`).**
Introduce `Widget` + `Param`. Rewrite `backend/routers/reports.py` and
`backend/agents/tools_footwear.py` as generators over a `WIDGETS` list defined
next to `services/footwear.py`. Unify `taric`→`heading`. Tests:
`test_reports_endpoint.py` + `test_tools_footwear.py` still green; add a test
that the generated tool def and REST route agree on param names.

**Step 2 — unified orchestrator (in `backend/`).**
Introduce `Domain` protocol + `run_chat`. Port `orchestrator_footwear.run` into
`run_chat` with `finalize()` = "last successful widget envelope". Reimplement
free-SQL as `SqlDomain` with a `structured_json` `finalize()`. Delete
`orchestrator.py` and `orchestrator_footwear.py`. Fix: always populate
`ChartEnvelope.data`; honor `AgentResult.hit_limit`; `meta.is_provisional` →
`meta.notes`. Tests: `test_orchestrator*.py` rewritten against `run_chat`; add a
test that the "Datos" payload is non-empty in domain mode.

**Step 3 — CSS tokenization + JS split (in `frontend/`).**
Tokenize all hex to `:root` custom properties. Split the inline `<script>` into
`web/chatkit.js` (shell, chat, widget grid, `registerTab`) served statically +
a ~60-line `web/index.html` that imports it. `login.html` → `mountLogin`. Add
`/api/app-config`; move branding/prompts/widget list/themes into it. Add a
headless smoke test (page boots, `/api/app-config` shape, widget grid renders N
cards).

**Step 4 — file move (pure).**
Create `packages/chatkit/` and `projects/footwear/`, move files per §3, fix
imports, `pip install -e packages/chatkit`. Zero behavior change. Split the test
suites. Add the CI dependency-direction check. Create `chatkit._demo`.

**Step 5 — project #2.**
Build the second domain against `chatkit`. Expect to find gaps; fix them in
`chatkit`, not by forking.

**Step 6 — version + topology review.**
Cut `chatkit` `0.1.0`. Decide repo split only if the extraction trigger fired.

## 14. Test strategy

| Suite | Fixture | Covers |
|---|---|---|
| `packages/chatkit/tests` | `chatkit._demo` (2-widget demo domain + demo duckdb) | `create_app` wiring, widget-route generation, `run_chat` control flow, `charts.build_option`, auth (`verify_google_token`, allowlist, session gate), `warehouse/duckdb`, `history.clean_history`, `/api/app-config` shape, headless frontend smoke |
| `projects/footwear/tests` | tiny in-memory datacomex duckdb (as today) | `services/footwear.py` SQL + envelopes, the `WIDGETS` list, `ingest/*`, `FootwearDomain.finalize`, `datacomex` seed |

- No `chatkit` test imports `projects.*`.
- The frontend gets at least a boot smoke test + a unit test of the
  config→widget-grid param binding (the highest-risk new logic).
- LLM calls: `chatkit._demo` injects a scripted fake client; the one live
  integration test stays skipped-by-default.

## 15. Risks (ranked)

1. **`chatkit.js` API surface.** Getting `mountChat` / `mountWidgetGrid` /
   `registerTab` right is the crux. Mitigation: Step 3 builds it *in the footwear
   repo first*, against the real reports panel, before any file move.
2. **`finalize()` abstraction leak.** The two current close-outs are more
   different than they look (argmax chartability vs last-envelope; ErrorEvent vs
   Text fallback). Mitigation: Step 2 lands with both `FootwearDomain` and
   `SqlDomain` green in the same suite.
3. **Import-time globals vs a factory.** `config` module-level + `llm._client`
   memo. Mitigation: `Settings` object threaded explicitly; delete the memo.
4. **`AUTH_DB_PATH` / committed data files.** `auth.sqlite` and the ~19 MB
   `footwear.duckdb` are in git. Mitigation: during Step 4, `git rm --cached`
   both, add to `.gitignore`, make `auth_db_path` required.
5. **Widget param mini-language creep.** `Param.type` + `ui_options_from` is
   enough for footwear; resist adding more until project #2 proves a need.
6. **Frontend has no tests today.** Mitigation: Step 3 adds the smoke + binding
   tests before the code becomes "core".

## 16. Out of scope

- Server-side per-user chat history (still `localStorage`).
- Multi-tenant single deploy (each project is its own deploy).
- npm-publishing `chatkit.js` (served by the package; no separate JS registry).
- i18n framework — `title`/`kpi.value`/`notes` are pre-localized by the domain.
- Admin UI, roles.
- A project generator / `copier` template (revisit at project #3).
