# Spec: Login con Google (Gmail) — Analista de Calzado

**Fecha:** 2026-09-04
**Estado:** Aprobado (pendiente revisión del spec)
**Rama:** `Calzados`

## 0. Objetivo

Poner la plataforma detrás de un login con Google para (a) restringir el acceso a
una lista de emails permitida y (b) saber quién la usa (tabla de usuarios + log de
sesiones). Requisito para subir a producción.

## 1. Decisiones (ya tomadas)

| Tema | Decisión |
|---|---|
| Flujo OAuth | **Google Identity Services (GIS)** — ID token (JWT). Sin redirect, sin client-secret, sin intercambio de código. |
| Acceso | **Allowlist de emails** (`ALLOWED_EMAILS`). Cualquier otro Google account → 403. |
| Sesión | **Cookie firmada por el backend** (`SessionMiddleware` de Starlette). HttpOnly, Secure, SameSite=Lax, 14 días. |
| Auditoría | **SQLite** (stdlib `sqlite3`): tabla `users` + `session_log`. |
| Despliegue | **Dokploy** en VPS. Traefik + Let's Encrypt dan HTTPS y dominio automáticamente. |

## 2. Arquitectura

```
frontend/login.html                     ← página pública: botón GIS
  │ google.accounts.id → credential (JWT)
  │ POST /auth/google { credential }
  ▼
backend/routers/auth.py
  ├── POST /auth/google   → verify + allowlist + set session cookie + record_login
  ├── GET  /auth/me       → { email, name } | 401
  ├── POST /auth/logout   → session.clear()
  └── GET  /auth/config    → { client_id }   (para que login.html no hardcodee nada)

backend/auth.py
  ├── verify_google_token(credential) -> {email, name, sub}   (google-auth)
  └── is_allowed(email) -> bool

backend/auth_db.py            ← SQLite, AUTH_DB_PATH
  ├── users(email PK, name, first_seen, last_seen, sessions)
  ├── session_log(id, email, at, user_agent)
  └── record_login(email, name, user_agent)

backend/app.py
  ├── add_middleware(SessionMiddleware, ...)
  └── @app.middleware("http") auth_gate     ← ver §4
```

**Regla:** toda la lógica de verificación vive en `backend/auth.py`. Los routers y
el middleware son wrappers finos.

## 3. Flujo de login

1. Usuario anónimo pide `/` → el gate lo redirige a `/login.html`.
2. `login.html` carga `https://accounts.google.com/gsi/client`, pide `/auth/config`
   para el `client_id`, renderiza el botón.
3. Al autenticarse, GIS invoca el callback con `response.credential` (JWT).
4. `POST /auth/google { credential }`:
   - `verify_google_token`: `google.oauth2.id_token.verify_oauth2_token(credential,
     google.auth.transport.requests.Request(), GOOGLE_CLIENT_ID)`. Valida firma,
     `aud`, `iss` (`accounts.google.com`), `exp`. Falla → 401.
   - `email = payload["email"].lower()`. Si `payload.get("email_verified")` es
     falso → 401.
   - `is_allowed(email)` falso → **403** `{ "error": "email no autorizado" }`.
   - `record_login(email, name, user_agent)`.
   - `request.session["user"] = { "email": email, "name": name }`.
   - Responde `200 { "email", "name" }`.
5. `login.html` hace `location = "/"`.

## 4. El gate (middleware HTTP)

```
PUBLIC_PREFIXES = ("/login.html", "/auth/", "/favicon", "/healthz")

async def auth_gate(request, call_next):
    if not config.AUTH_ENABLED:
        request.state.user = {"email": "dev@localhost", "name": "Dev"}
        return await call_next(request)
    if request.url.path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)
    user = request.session.get("user")
    if not user:
        if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"error": "auth required"}, status_code=401)
        return RedirectResponse("/login.html")
    request.state.user = user
    return await call_next(request)
```

- `AUTH_ENABLED=false` (default en dev/test) → inyecta un usuario dev y **nunca
  bloquea**. Los 102 tests actuales pasan sin tocar nada y sin credenciales de
  Google.
- Orden de middlewares: `SessionMiddleware` primero (más externo), luego el gate,
  de modo que `request.session` esté disponible en el gate.
- El gate corre **antes** del mount de estáticos y de los routers, así protege
  también `index.html` y los assets.

## 5. Auditoría (`auth_db.py`)

SQLite en `AUTH_DB_PATH` (default `backend/warehouse/auth.sqlite`). Se crea al
importar si no existe.

```sql
CREATE TABLE IF NOT EXISTS users (
    email      TEXT PRIMARY KEY,
    name       TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    sessions   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS session_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL,
    at         TEXT NOT NULL,
    user_agent TEXT
);
```

`record_login(email, name, user_agent)`:
- `INSERT INTO users ... ON CONFLICT(email) DO UPDATE SET name=excluded.name,
  last_seen=..., sessions=sessions+1` (con `first_seen` fijado sólo en el insert).
- `INSERT INTO session_log (email, at, user_agent) VALUES (...)`.

Conexiones: una por operación (`sqlite3.connect(path)` es barato), `check_same_thread`
no aplica porque no compartimos conexión. Sin panel de admin en esta fase — se
consulta con `sqlite3 auth.sqlite`.

## 6. Frontend

### `frontend/login.html` (nuevo)
- Estilo mínimo reusando IBM Plex + la paleta.
- `fetch("/auth/config")` → `client_id`.
- `google.accounts.id.initialize({ client_id, callback })` + `renderButton`.
- callback → `POST /auth/google` → 200 → `location = "/"`; 403 → mensaje "email no
  autorizado, contacta al administrador".

### `frontend/index.html`
- Al arrancar: `const me = await fetch("/auth/me")`. Si `!me.ok` → `location =
  "/login.html"`. Si OK → guardar `{email, name}` y arrancar la app.
- Footer del sidebar (`.sb-foot`): mostrar `name` + un botón "Cerrar sesión" →
  `POST /auth/logout` → `location = "/login.html"`.
- Colapsado: el footer se oculta (ya lo hace vía `.sb-hideable`).

## 7. Config (`config.py`)

```python
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-insecure-secret")
ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}
AUTH_DB_PATH = Path(os.environ.get("AUTH_DB_PATH",
    str(Path(__file__).parent / "warehouse" / "auth.sqlite")))
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", str(60 * 60 * 24 * 14)))
```

Arranque: si `AUTH_ENABLED` y (`GOOGLE_CLIENT_ID` vacío o `SESSION_SECRET` es el
default o `ALLOWED_EMAILS` vacío) → log de warning claro (no crashea, pero avisa).

## 8. Despliegue en Dokploy

1. **App en Dokploy**: apuntar al repo/rama `Calzados`, build con el `Dockerfile`
   existente. Puerto interno 8000.
2. **Dominio**: asignar el dominio en Dokploy → Traefik emite el certificado TLS.
3. **Env vars** (en Dokploy → Environment):
   ```
   LLM_PROVIDER=deepseek
   DEEPSEEK_API_KEY=...
   AUTH_ENABLED=true
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   SESSION_SECRET=<openssl rand -hex 32>
   ALLOWED_EMAILS=david@...,otro@...
   ```
4. **Volumen**: montar un volumen Dokploy en `/app/backend/warehouse/auth.sqlite`
   (o en `/app/data` con `AUTH_DB_PATH=/app/data/auth.sqlite`) para que el registro
   de usuarios sobreviva redeploys. Los warehouses (`footwear.duckdb`, demo) van
   horneados en la imagen y no necesitan volumen.
5. **Google Cloud Console** → APIs & Services → Credentials → el OAuth 2.0 Client ID:
   - *Authorized JavaScript origins*: `https://<tu-dominio>` (y `http://localhost:8000`
     para dev).
   - No hacen falta *redirect URIs* (flujo GIS).
   - El *Client Secret* no se usa.

## 9. Riesgos / detalles del stack

1. **`SessionMiddleware` + `https_only=True`**: en local (http) la cookie no se
   set-ea. Para dev usamos `AUTH_ENABLED=false`, así que no molesta. En prod detrás
   de Traefik el request llega como https → OK. (Si Traefik termina TLS y reenvía
   http, Starlette ve http → necesitamos `ProxyHeadersMiddleware` /
   `--forwarded-allow-ips` en uvicorn para que `request.url.scheme` sea https, o
   poner `https_only=False` y confiar en `SameSite`+`Secure` vía proxy. Decisión:
   añadir `--proxy-headers` al CMD de uvicorn y `https_only=True`.)
2. **`google-auth`** hace una llamada de red a los certs de Google (con caché). En
   tests se mockea `verify_oauth2_token` — cero red.
3. **Reloj**: `verify_oauth2_token` rechaza tokens si el reloj del server está muy
   desfasado. `clock_skew_in_seconds=10` de margen.
4. **CSRF**: `SameSite=Lax` + que `/auth/google` sólo acepte el `credential` (que
   un atacante no puede forjar) cubre el caso. `/auth/logout` es POST.
5. **`AUTH_DB_PATH` en la imagen**: si no hay volumen, `auth.sqlite` se pierde en
   cada redeploy (no rompe, sólo se pierde el histórico). El spec pide volumen.

## 10. Tests

| Test | Qué verifica |
|---|---|
| `test_verify_google_token_ok` | monkeypatch `verify_oauth2_token` → devuelve `{email,name,sub}` |
| `test_verify_google_token_bad` | el verificador lanza → propaga como error de auth |
| `test_is_allowed` | allowlist case-insensitive; vacío = nadie |
| `test_auth_google_sets_session_and_records_login` | POST con token válido+permitido → 200, cookie, fila en `users`/`session_log` |
| `test_auth_google_rejects_non_allowlisted` | email válido pero fuera de allowlist → 403 |
| `test_gate_blocks_api_without_session` | `GET /api/v1/reports/...` sin cookie → 401 |
| `test_gate_redirects_html_without_session` | `GET /` sin cookie → 307 → `/login.html` |
| `test_gate_open_when_auth_disabled` | `AUTH_ENABLED=false` → `/` y `/api/*` pasan; `/auth/me` = dev user |
| `test_me_and_logout` | login → `/auth/me` OK → `/auth/logout` → `/auth/me` 401 |
| `test_record_login_upserts` | segundo login del mismo email: `sessions` sube, `first_seen` no cambia |

Los tests que hoy usan `TestClient` sin auth siguen pasando porque `AUTH_ENABLED`
default es `false`.

## 11. Archivos

| Archivo | Cambio |
|---|---|
| `backend/auth.py` | nuevo — `verify_google_token`, `is_allowed` |
| `backend/auth_db.py` | nuevo — SQLite `users` / `session_log`, `record_login` |
| `backend/routers/auth.py` | nuevo — `/auth/{google,me,logout,config}` |
| `backend/app.py` | `SessionMiddleware` + `auth_gate` + registrar router |
| `backend/config.py` | `AUTH_ENABLED`, `GOOGLE_CLIENT_ID`, `SESSION_SECRET`, `ALLOWED_EMAILS`, `AUTH_DB_PATH`, `SESSION_MAX_AGE` |
| `frontend/login.html` | nuevo |
| `frontend/index.html` | check `/auth/me` al cargar; usuario + "Cerrar sesión" en el footer |
| `requirements.txt` | `+ google-auth` |
| `Dockerfile` | `CMD` con `--proxy-headers --forwarded-allow-ips="*"` |
| `.env.example` | bloque de auth |
| `README.md` | sección "Autenticación" + pasos Dokploy / Google Console |
| `tests/test_auth.py` | nuevo — §10 |

## 12. Fuera de alcance (esta fase)

- Panel de administración de usuarios en la UI.
- Roles / permisos (todos los emails de la allowlist tienen el mismo acceso).
- Refresh tokens / "recordar sesión" más allá de los 14 días.
- Rate limiting.
- Otros proveedores (Microsoft, magic link).
