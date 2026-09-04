# Spec: Módulo DataComex Calzado — adaptada al stack actual

## 0. Stack confirmado

- Backend: FastAPI + Pydantic, streaming SSE manual, DuckDB embebido (read-only), agentes con tool-use manual.
- Frontend: `index.html` vanilla JS + ECharts 5 (CDN), sin build step.
- Implicación directa: la capa de datos y de gráficos se agregan como **servicios Python puras** que sirven tanto a los endpoints REST como a las tools del agente. Un solo código, dos consumidores.

---

## 1. Arquitectura objetivo

```
ingest/                          ← PROCESO OFFLINE (escribe, app NO escribe nunca)
├── fetch_datacomex.py           # API DataComex / descarga masiva CSV → staging
└── build_warehouse.py           # staging → datacomex.duckdb (modo escritura)

app/                             ← SERVIDOR (DuckDB read-only, como hoy)
├── warehouse.py                 # conexión DuckDB existente, añadir attach de datacomex.duckdb
├── services/
│   └── footwear.py              # ÚNICA capa de queries + builder de chartSpec
├── routers/
│   └── reports.py               # GET /api/v1/reports/footwear/{widget}
└── agents/
    ├── tools_footwear.py        # tools del agente → llaman a services/footwear.py
    └── orchestrator.py          # registrar tools existentes (sin cambios de loop)

frontend/
├── index.html                   # chat existente (sin cambios estructurales)
└── reportes-calzado.html        # nueva página (o sección si prefieres monolito)
```

**Regla de oro**: `services/footwear.py` es el único lugar con SQL del dominio. Los endpoints y las tools son wrappers finos. Así el chat y la página nunca divergen.

---

## 2. Modelo de datos (DuckDB)

```sql
CREATE SCHEMA IF NOT EXISTS datacomex;

CREATE TABLE datacomex.trade_flows (
    flow          VARCHAR NOT NULL,          -- 'IMPORT' | 'EXPORT'
    period        VARCHAR NOT NULL,          -- 'YYYY-MM'
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    country_code  VARCHAR NOT NULL,          -- ISO/a3 DataComex
    country_name  VARCHAR NOT NULL,
    taric_code    VARCHAR NOT NULL,          -- hasta 10 dígitos, se consulta a nivel 6
    chapter       VARCHAR NOT NULL,          -- '64'
    heading       VARCHAR NOT NULL,          -- '6403'
    value_eur     BIGINT NOT NULL,
    weight_kg     BIGINT NOT NULL,
    suppl_units   BIGINT,                    -- pares; NULL si la partida no reporta
    is_provisional BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE datacomex.taric_tree (
    code        VARCHAR PRIMARY KEY,         -- '64', '6403', '640411', ...
    parent_code VARCHAR,
    level       INTEGER NOT NULL,            -- 2 | 4 | 6
    description VARCHAR NOT NULL             -- ES
);

CREATE TABLE datacomex.meta_ingestion (
    id           INTEGER PRIMARY KEY,
    loaded_at    TIMESTAMP NOT NULL,
    period_max   VARCHAR NOT NULL,
    rows_loaded  INTEGER NOT NULL,
    source       VARCHAR NOT NULL            -- 'api' | 'csv_masiva'
);
```

Consultas agregan hacia arriba en tiempo de query (DuckDB lo hace volando):

```sql
-- W2: ranking de países, partida completa por defecto
SELECT country_name, SUM(value_eur) AS total_eur
FROM datacomex.trade_flows
WHERE flow = ? AND chapter = '64' AND period BETWEEN ? AND ?
GROUP BY country_name
ORDER BY total_eur DESC
LIMIT 10;
```

**Filtro de granularidad clave**: almacenar solo nivel 6 y filtrar `heading = '6403'` para partidas; `chapter = '64'` para el capítulo. Nunca persistir agregados derivados.

---

## 3. Contrato chartSpec → ECharts

El servidor devuelve ECharts option ya montada + KPIs. El frontend hace `chart.setOption(spec.echarts)` y nada más.

```json
GET /api/v1/reports/footwear/evolution?flow=EXPORT&taric=64&months=24
{
  "widget": "monthly_evolution",
  "title": "Exportaciones de calzado — últimos 24 meses",
  "echarts": {
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": ["2024-09", "2024-10", "..."]},
    "yAxis": {"type": "value", "name": "M€"},
    "series": [
      {"name": "2024-25", "type": "line", "smooth": true, "data": [245.1, ...]},
      {"name": "2025-26", "type": "line", "smooth": true, "data": [null, ..., 238.2]}
    ]
  },
  "kpis": [
    {"label": "Var. interanual", "value": "+3.2%", "tone": "positive"}
  ],
  "meta": {"unit": "EUR", "granularity": "monthly", "is_provisional": true}
}
```

Mapeo tipo→option (builder en `services/footwear.py`):
- `monthly_evolution` → line, dos series desplazadas 12M para YoY
- `country_ranking` → bar horizontal (top N)
- `product_mix` → donut sobre 6401–6406
- `avg_price` → line de €/kg (guard: `weight_kg > 0`, fallback €/t)
- `trade_balance` → bar (saldo) + line (acumulado)

---

## 4. Endpoints REST

| Método | Ruta | Params | Devuelve |
|---|---|---|---|
| GET | `/api/v1/reports/footwear/filters/options` | — | periodos disponibles, países top, partidas 64xx (para poblar selectores) |
| GET | `/api/v1/reports/footwear/evolution` | flow, taric, months | chartSpec |
| GET | `/api/v1/reports/footwear/countries` | flow, taric, period_from, period_to, top_n | chartSpec |
| GET | `/api/v1/reports/footwear/product-mix` | flow, period_from, period_to | chartSpec |
| GET | `/api/v1/reports/footwear/avg-price` | flow, taric, country?, months | chartSpec |
| GET | `/api/v1/reports/footwear/balance` | taric, months | chartSpec |

Todos devuelven el mismo envelope `{widget, title, echarts, kpis, meta}` — el front de reportes es un grid genérico que consume endpoints por configuración.

---

## 5. Tools para el agente (tool-use manual actual)

Registro declarativo, mismo estilo que las tools existentes:

```python
# agents/tools_footwear.py
from services.footwear import evolution, country_ranking, product_mix, avg_price, resolve_taric

TOOLS = [
    {
        "name": "footwear_market_overview",
        "description": "Evolución de importaciones/exportaciones de calzado (cap. TARIC 64) en valor. Usar cuando el usuario pida tendencia, evolución o 'cómo va' el comercio de calzado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flow": {"type": "string", "enum": ["IMPORT", "EXPORT"]},
                "heading": {"type": "string", "pattern": "^64\\d{2}$"},
                "months": {"type": "integer", "default": 24}
            },
            "required": ["flow"]
        },
        "handler": evolution
    },
    {
        "name": "footwear_top_partners",
        "description": "Ranking de países origen/destino por valor. Usar para 'de dónde importamos' o 'a dónde exportamos'.",
        ...
    },
    {
        "name": "resolve_footwear_product",
        "description": "Busca el código TARIC de un tipo de calzado descrito en lenguaje natural (ej. 'deportivas' → 6404). LLAMAR SIEMPRE antes si el usuario usa términos coloquiales.",
        ...
    },
]
```

**Reglas de prompt (bloque de sistema añadido, no reescrito):**
1. Término coloquial de producto → `resolve_footwear_product` primero.
2. Pregunta de evolución/ranking/mix → tool correspondiente, y la respuesta **incluye el chartSpec** (el front ya renderiza gráficos en el chat si hay un bloque chart; si no, F3 lo añade con el mismo renderer de ECharts).
3. Nunca generar SQL libre; solo estas tools.
4. Si `meta.is_provisional = true`, mencionar "datos provisionales".

Las handlers devuelven el mismo dict que los endpoints → el agente puede pasar `result["echarts"]` tal cual al front.

---

## 6. Frontend: página de reportes

- Opción recomendada: sección nueva en el `index.html` existente (toggle chat/reportes) para no romper el patrón monolítico y reutilizar estilos, IBM Plex y el renderer ECharts.
- Grid de widgets definido en un array de configuración JS:
  ```js
  const WIDGETS = [
    {id: "w1", endpoint: "/evolution", title: "Evolución mensual", span: 2},
    {id: "w2", endpoint: "/countries", title: "Principales socios", span: 2},
    {id: "w3", endpoint: "/product-mix", title: "Mix de producto", span: 1},
    {id: "w4", endpoint: "/avg-price", title: "Precio medio €/kg", span: 1},
    {id: "w5", endpoint: "/balance", title: "Saldo comercial", span: 2},
  ];
  ```
- Barra de filtros globales (periodo, flujo, partida, país) que dispara refetch de todos los widgets.
- Reutilizar función `renderChart(domId, echartsOption)` para página Y chat.

---

## 7. Plan por fases

| Fase | Dur. | Tareas | Entregable |
|---|---|---|---|
| **F0 Ingesta** | 4-5 días | Registro DataComex; descarga CSV masiva histórica cap. 64; `build_warehouse.py`; precargar `taric_tree`; validar contra cifra pública (exportación 2025 ≈ 3.056 M€) | `datacomex.duckdb` poblado + checksum OK |
| **F1 Servicios** | 3-4 días | `services/footwear.py` con 5 builders de chartSpec; tests de cada query contra totales conocidos | Endpoints devolviendo chartSpec en dev |
| **F2 Página** | 1 semana | Filtros globales, grid de widgets, renderer ECharts compartido | `/reportes/calzado` navegable con datos reales |
| **F3 Chat** | 4-5 días | `tools_footwear.py`, registro en orquestador, bloque de prompt, render de chartSpec en mensajes | "¿Cómo fueron las exportaciones de deportivas en 2025?" → gráfico en el chat |
| **F4 Pulido** | 3-4 días | Job mensual de actualización (cron local o GitHub Action) con alerta si falla; estados loading/error; indicador "provisional" | Demo lista para el cliente |

**Ruta crítica**: F0. Mientras se valida la ingesta, se puede avanzar F1 sobre datos sintéticos con el mismo schema (ya tienes generador determinista — perfecto para TDD de los builders).

---

## 8. Riesgos específicos del stack

1. **DuckDB read-only**: la app nunca escribe; `build_warehouse.py` corre offline y reemplaza el archivo (o usa `ATTACH` + swap). Si el job mensual falla, la app sigue sirviendo el último archivo bueno.
2. **CSV masiva de DataComex**: codificación y separador pueden variar → sniffing con `csv.Sniffer` + aserciones de columnas esperadas en el loader.
3. **SSE + tools**: si una tool tarda (query pesada), el agente hace el llamado fuera del stream y solo el texto final va por SSE (patrón que ya tienen con `threading/queue`).
4. **ECharts en CDN**: la página de reportes offline/no-network caería sin gráficos → vendorizar `echarts.min.js` local en F4 si el cliente lo va a usar en demo presencial.

## 9. Decisiones pendientes (tu lado)

- [ ] ¿Sección en `index.html` o página separada? (recomendado: sección)
- [ ] ¿Job mensual manual, cron, o GitHub Action? (recomendado: Action con artifact del .duckdb)
- [ ] ¿Cargar solo cap. 64 o también componentes (cap. 42 cueros, cap. 40 caucho) para análisis de cadena de valor? (fase 2)
