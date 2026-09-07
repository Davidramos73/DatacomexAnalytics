# chatkit + Analista de Calzado

A reusable chat-analytics core (`chatkit`) and a thin deployable project built on
it — **Analista de Calzado**, which answers natural-language questions about
Spanish footwear foreign trade (DataComex, TARIC chapter 64) and returns an
Apache ECharts chart, rendered by a minimal web UI.

- **`chatkit`** — a domain-agnostic package: a `Domain` protocol, a `create_app()`
  factory, the LLM agent loop + SSE streaming, Google-login auth, a `Widget`
  descriptor that generates the REST route + chat tool + frontend descriptor from
  one declaration, and the deterministic ECharts option builder.
- **`projects/footwear/`** — implements one `Domain` (`FootwearDomain`): the
  DataComex SQL, five typed report tools, branding. `main.py` is
  `app = create_app(FootwearDomain())`.
- **UI** — a ~26-line project `index.html` that imports `chatkit.js` and is driven
  entirely by `/api/app-config`; streams the tool-trace and renders each chart
  inline with Chart / Spec / Data tabs.

`chatkit` also ships an optional free-SQL `SqlDomain` (an orchestrator agent that
writes read-only SQL and designs a chart) used by the `_demo` fixture domain.

## Layout

```
packages/chatkit/     pip-installable core — Domain protocol, create_app() factory,
                      agents, auth, widgets, charts, frontend assets
projects/footwear/    the thin deployable project: FootwearDomain + main.py
                      (app = create_app(FootwearDomain()))
```

`packages/chatkit` must never import `projects.*` — `make check-deps` enforces it.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e packages/chatkit
cp .env.example .env    # set LLM_PROVIDER + its API key (the deploy uses deepseek)
```

## Run locally

```bash
export PYTHONPATH=$PWD          # so `import projects.footwear` resolves
uvicorn projects.footwear.main:app --port 8000
# open http://localhost:8000
```

The app reads its DuckDB from `DATACOMEX_PATH` (default: the checked-in demo
warehouse at `projects/footwear/warehouse/footwear.duckdb`); it imports and boots
fine with no DB present.

## Docker

```bash
cp .env.example .env
docker compose up --build
# open http://localhost:8000
```

Nothing is baked into the image. The real warehouse is supplied at runtime via a
mounted volume (`datacomex-data` → `/app/data`), with
`DATACOMEX_PATH=/app/data/footwear.duckdb` and `AUTH_DB_PATH=/app/data/auth.sqlite`.

Plain Docker:
`docker build -t footwear-analyst . && docker run --env-file .env -v datacomex-data:/app/data -p 8000:8000 footwear-analyst`

## Provider

Default provider is Anthropic (`claude-opus-5`). OpenAI-compatible alternatives:

```bash
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=sk-or-...

export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-...
```

Override the model with `LLM_MODEL` / `DATA_AGENT_MODEL`.

## Auth (Google login)

`AUTH_ENABLED=false` (default) leaves everything open — for local dev and the
test suite. In production:

```bash
AUTH_ENABLED=true
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
SESSION_SECRET=$(openssl rand -hex 32)
ALLOWED_EMAILS=you@example.com,teammate@example.com
AUTH_DB_PATH=/app/data/auth.sqlite      # on a persistent volume
```

`login.html` → Google returns an ID token → `POST /auth/google` verifies it,
checks `ALLOWED_EMAILS`, records the login in SQLite, sets a signed session
cookie. A gate middleware 401s API calls / redirects HTML without a session.

## Tests

```bash
pytest packages/chatkit/tests projects/footwear/tests -q   # both suites, no API key
make check-deps                                            # dependency direction
node --test packages/chatkit/chatkit/frontend/             # chatkit.js unit tests
```

## Starting a new project on chatkit

Implement the `Domain` protocol from `chatkit` (schema, `open_connection()`,
`web_dir()`, branding, widgets, extra routes) in your own `projects/<name>/`
package, then expose `app = create_app(YourDomain())` in a `main.py`. Copy
`projects/footwear/` as a template; the core package needs no changes.
