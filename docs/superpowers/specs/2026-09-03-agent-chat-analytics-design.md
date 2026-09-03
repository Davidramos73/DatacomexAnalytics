# Agent Chat Analytics — Design

**Date:** 2026-09-03
**Status:** Approved (pending spec review)

## Goal

Backend multi-agente + UI mínima que reproduce el flujo del mockup `Agent Chat.dc.html`:
el usuario hace una consulta en lenguaje natural → un agente orquestador delega en un
agente con conocimiento del schema → ese agente ejecuta SQL read-only contra la base →
devuelve filas → el orquestador las convierte en una spec Vega-Lite → la UI la renderiza
inline, mostrando el tool-trace (pasos `schema.lookup` → `sql.query` → `chart.render`).

## No-goals (YAGNI)

- Persistencia de chats / múltiples threads / gestión del sidebar (el mockup lo tiene
  mockeado; no aporta al flujo end-to-end). La UI corre un solo thread en memoria.
- Autenticación, multiusuario, rate limiting.
- Escritura a la base. Todo es read-only.
- Reutilizar el runtime DC (`support.js`): está pensado para el canvas de Claude Design;
  correrlo standalone es frágil. La UI se reescribe en vanilla JS reusando el CSS.

## Arquitectura

```
Browser (frontend/index.html)
  │  POST /api/chat {session_id, message}  →  text/event-stream (SSE)
  ▼
FastAPI (backend/app.py)  ── sirve frontend/ estático + el endpoint
  ▼
Orquestador (backend/agents/orchestrator.py)
  • Claude, loop de tool-use manual
  • tool: query_data(question: str)  → invoca al agente de datos
  • cierre: llamada con output_config.format (json_schema) →
      { answer: str, chart_title: str, vega_lite_spec: object }
  ▼
Agente de datos (backend/agents/data_agent.py)
  • Claude, loop de tool-use manual
  • system prompt con el schema introspeccionado + SCHEMA_NOTES
  • tools: get_schema()  ·  run_sql(sql: str)
  • retorna { sql, columns, rows, row_count }
  ▼
DuckDB (backend/warehouse/warehouse.duckdb)  ── read_only=True, datos sintéticos
```

## Componentes

### `backend/warehouse/`

- **`seed.py`** — script idempotente que (re)construye `warehouse.duckdb`. Tablas:
  - `dim_region(region, macro_area)`
  - `fct_orders(order_id, order_date, quarter, week, region, channel, segment, net_revenue, discount_pct, gross_margin_pct)`
  - `mart_account_health(segment, avg_discount, gross_margin, accounts)`
  Datos sintéticos generados con `random` sembrado (determinista), volúmenes parecidos al
  mockup (~miles de filas en `fct_orders`). Se ejecuta con `python -m backend.warehouse.seed`.
- **`schema.py`** —
  - `introspect(conn) -> str`: arma un listado `tabla(col tipo, ...)` desde
    `information_schema.columns`.
  - `SCHEMA_NOTES: str`: constante escrita a mano con el grano de cada tabla, unidades
    (`net_revenue` en USD, `gross_margin_pct` 0–100), y qué columna usar para qué pregunta.
  - `schema_context(conn) -> str`: `introspect()` + `SCHEMA_NOTES` + 3 filas de muestra por
    tabla (`SELECT * ... LIMIT 3`).
- **`db.py`** —
  - `connect() -> DuckDBPyConnection`: abre `warehouse.duckdb` con `read_only=True`.
  - `run_sql(conn, sql: str, *, max_rows: int = 500, timeout_s: float = 10) -> dict`:
    - Normaliza: `strip()`, saca `;` final.
    - Rechaza (`ValueError`) si: no empieza con `SELECT` o `WITH` (case-insensitive tras
      quitar comentarios); contiene `;` (múltiples statements); matchea
      `\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|COPY|PRAGMA|INSTALL|LOAD)\b`.
    - Si no hay `LIMIT` en el nivel superior, envuelve: `SELECT * FROM (<sql>) LIMIT <max_rows+1>`.
    - Ejecuta; si vuelven `> max_rows`, marca `truncated: true` y capa.
    - Devuelve `{ sql, columns: [str], rows: [[val]], row_count: int, truncated: bool }`.
    - `timeout_s` vía `conn.execute("SET statement_timeout=...")` o thread con cancel.

### `backend/agents/llm.py`

- `client = anthropic.Anthropic()` (credenciales del entorno; no hardcodear).
- `EventSink`: callback `emit(event: Event)` que el runner usa para publicar SSE.
- `run_agent(*, system, messages, tools, tool_impls, sink, model, max_iters=6,
  step_label_for) -> AgentResult`:
  loop manual `while stop_reason == "tool_use"` (ref: skill claude-api, "Manual Agentic
  Loop"). Por cada `tool_use`: emite un evento `step` (label derivado del nombre de tool),
  ejecuta `tool_impls[name](**input)`, arma `tool_result` (con `is_error: True` en excepción).
  Corta en `end_turn`, `pause_turn` (re-emite), o al llegar a `max_iters` (emite `error`).
  Thinking adaptativo (`thinking={"type": "adaptive"}`). `max_tokens=16000`.
- `AgentResult`: `{ final_text, messages, iterations, tool_calls: [ {name, input, result} ] }`.

### `backend/agents/data_agent.py`

- `answer_data_question(question: str, sink: EventSink) -> DataResult`
- System prompt: rol de analista, `schema_context(conn)`, reglas (solo SELECT, preferir
  agregaciones, nombrar columnas de salida legibles).
- Tools:
  - `get_schema()` → `schema_context(conn)` (emite `step schema.lookup`).
  - `run_sql(sql)` → `db.run_sql(...)` serializado a JSON (emite `step sql.query` con el
    SQL como `detail`).
- Tras el loop: toma el **último `run_sql` exitoso** de `tool_calls` como el dataset.
  Si no hubo ninguno → `DataResult(ok=False, error=...)`.
- `DataResult`: `{ ok, sql, columns, rows, row_count, truncated, notes: final_text, error }`.

### `backend/agents/orchestrator.py`

- `run(user_message: str, sink: EventSink) -> None` — orquesta y emite todos los eventos
  de la respuesta.
- System prompt: rol, explica que tiene un analista de datos detrás y que su trabajo es
  (1) formular la/s pregunta/s de datos, (2) explicar el resultado en prosa breve,
  (3) proponer un chart Vega-Lite v5 apropiado.
- Tool única: `query_data(question: str)` → llama `data_agent.answer_data_question`,
  devuelve a Claude un JSON con `columns`, `rows` (capadas), `row_count`, `sql`, `notes`.
- Después de que el loop de tool-use termina (Claude ya tiene los datos), **llamada final**
  con `output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}}`:
  - `RESPONSE_SCHEMA`: objeto con `answer` (string), `chart_title` (string),
    `chart_meta` (string, p.ej. `"bar · fct_orders · 5 rows"`),
    `vega_lite_spec` (objeto, `additionalProperties: true`).
  - Se le pasa como contexto el dataset elegido (el del último `query_data`).
- Validación de la spec (`_validate_vega_lite(spec, data_rows)`):
  - tiene `"$schema"` con `vega-lite`; tiene `mark` **o** `layer`; tiene `encoding` (o en
    cada layer). Si la spec trae `data.values` vacío o `data: {"name": ...}`, se
    reemplaza por `{"values": rows_as_records}` usando las filas del dataset.
  - Si falla → emite `error {message}` (el mockup ya pinta ese estado) y termina.
- Emite en orden: `thinking` → (`step`s del data agent, vía el mismo sink) →
  `text {answer}` → `chart {title, meta, spec, data:{columns, rows}}` → `done {seconds}`.

### `backend/events.py`

`@dataclass` por tipo con `.to_sse() -> str` (`f"event: {type}\\ndata: {json}\\n\\n"`):
`Step(label, detail)`, `Thinking(label)`, `Text(text)`,
`Chart(title, meta, spec, data)`, `ErrorEvent(message)`, `Done(seconds)`.

### `backend/app.py`

- `FastAPI()`. `GET /` y estáticos → `frontend/`.
- `POST /api/chat` body `{session_id: str, message: str}` → `StreamingResponse(gen(),
  media_type="text/event-stream")`. `gen()` corre el orquestador en un thread /
  `asyncio.to_thread`, con una `queue.Queue` como sink; cada item se yield-ea como SSE.
  Excepción no controlada → evento `error` + `done`.
- CORS abierto (dev).

### `backend/config.py`

`LLM_MODEL` (default `claude-opus-5`), `DATA_AGENT_MODEL` (default = `LLM_MODEL`),
`MAX_AGENT_ITERS` (6), `SQL_MAX_ROWS` (500), `WAREHOUSE_PATH`. Todo overridable por env.

### `frontend/index.html`

Página única, vanilla JS. Reusa el `<style>` del mockup. Estructura:

- Header con título estático + badge `warehouse · read only`.
- Thread: burbujas de usuario; bloques de agente con tool-trace colapsable (`steps[]`),
  prosa, y tarjeta de chart.
- Tarjeta de chart: tabs **Chart / Spec / Data**, estado loading (shimmer), estado error
  (con texto del error), botón expandir → modal. Render con `vegaEmbed(el, spec,
  {actions:false, renderer:"svg"})`.
- Composer: textarea + enviar. `Enter` envía.
- `send()`: `fetch("/api/chat", {method:POST, body})`, lee el stream con
  `response.body.getReader()` + `TextDecoder`, parsea eventos SSE y actualiza el DOM del
  mensaje de agente en curso.
- CDN: `vega@5`, `vega-lite@5`, `vega-embed@6` (mismos que el mockup).
- Sin sidebar de chats, sin persistencia.

## Flujo de datos (ejemplo)

1. Usuario: "¿Cómo se repartió el revenue de Q3 por región? Graficá."
2. Orquestador → `query_data("net revenue Q3 2026 por región, descendente")`.
3. Data agent → `get_schema()` → `run_sql("SELECT region, SUM(net_revenue)/1e6 AS revenue_m FROM fct_orders WHERE quarter='2026Q3' GROUP BY 1 ORDER BY 2 DESC")`.
4. Data agent retorna 5 filas + el SQL.
5. Orquestador (llamada final con schema) → `{answer: "...", chart_title: "Q3 net revenue by region", chart_meta: "bar · fct_orders · 5 rows", vega_lite_spec: {mark:"bar", encoding:{...}}}`.
6. `_validate_vega_lite` OK, inyecta `data.values` con las 5 filas.
7. SSE: `text` + `chart` + `done`. La UI renderiza la barra.

## Errores

| Caso | Manejo |
|---|---|
| `run_sql` con SQL no-SELECT | `run_sql` lanza `ValueError`; se devuelve como `tool_result is_error`; el data agent reintenta |
| Data agent nunca ejecuta SQL válido | `DataResult(ok=False)`; orquestador emite `error` |
| Spec Vega-Lite inválida | `_validate_vega_lite` falla → evento `error` con el detalle (UI lo pinta) |
| Loop supera `MAX_AGENT_ITERS` | runner emite `error` y corta |
| Excepción de la API de Anthropic | capturada en `app.gen()` → evento `error` + `done` |
| `ANTHROPIC_API_KEY` ausente | `app.py` falla al arrancar con mensaje claro |

## Testing

- **`tests/test_warehouse.py`**: `seed` crea las 3 tablas con filas > 0; `run_sql` rechaza
  `DELETE`/`UPDATE`/multi-statement/`DROP`; inyecta `LIMIT`; capa a `max_rows` y marca
  `truncated`.
- **`tests/test_data_agent.py`**: LLM falso (secuencia scripteada de respuestas con
  `tool_use` → `run_sql` → `end_turn`) inyectado en `llm.client`; verifica que
  `DataResult.rows` sale de la ejecución real contra una DuckDB de test.
- **`tests/test_orchestrator.py`**: `data_agent` falso + LLM falso (respuesta final JSON
  con una spec válida); verifica que se emite un evento `chart` y que la spec pasa
  `_validate_vega_lite`; y un caso de spec inválida → evento `error`.
- **`tests/test_endpoint.py`**: `TestClient`, orquestador falso que emite una secuencia
  fija; verifica el orden y el formato SSE de los eventos.
- **`tests/test_integration.py`**: gateado por `ANTHROPIC_API_KEY` (skip si falta); una
  consulta real end-to-end contra la warehouse sembrada, asserta que llega un `chart` con
  spec válida.
- TDD: cada componente se escribe test-first.

## Layout final

```
backend/
  __init__.py
  app.py
  config.py
  events.py
  agents/
    __init__.py
    llm.py
    orchestrator.py
    data_agent.py
  warehouse/
    __init__.py
    seed.py
    schema.py
    db.py
frontend/
  index.html
tests/
  __init__.py
  conftest.py
  test_warehouse.py
  test_data_agent.py
  test_orchestrator.py
  test_endpoint.py
  test_integration.py
requirements.txt        # anthropic, fastapi, uvicorn, duckdb, pytest, httpx
.env.example            # ANTHROPIC_API_KEY=
README.md               # seed + run + costo real por request
```

## Notas de implementación

- SDK: `anthropic` (Python), loop de tool-use **manual** (no el tool_runner beta) porque
  necesitamos interleave de eventos SSE por cada tool call y evitar dependencia beta.
- Modelo: `claude-opus-5`, thinking adaptativo. Cada request al endpoint gasta tokens
  reales — documentado en el README.
- `output_config.format` (json_schema) para la respuesta final del orquestador — garantiza
  JSON parseable con la spec.
```
