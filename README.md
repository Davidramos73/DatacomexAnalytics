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
