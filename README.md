# Agent Chat Analytics

Multi-agent backend that answers natural-language questions about an analytics
warehouse and returns an Apache ECharts chart, rendered by a minimal web UI.

- **Orchestrator agent** — turns your question into data questions, then designs a chart.
- **Data agent** — knows the schema, writes and runs read-only SQL against DuckDB.
- **UI** — streams the tool-trace (schema lookup → SQL → chart) and renders the spec inline.

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
cp .env.example .env    # then put your key in ANTHROPIC_API_KEY
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
ANTHROPIC_API_KEY=sk-... pytest packages/chatkit/tests/test_integration.py
```

## Starting a new project on chatkit

Implement the `Domain` protocol from `chatkit` (schema, `open_connection()`,
`web_dir()`, branding, widgets, extra routes) in your own `projects/<name>/`
package, then expose `app = create_app(YourDomain())` in a `main.py`. Copy
`projects/footwear/` as a template; the core package needs no changes.
