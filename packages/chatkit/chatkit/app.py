"""`create_app(domain)` — the chatkit ASGI application factory.

chatkit is domain-agnostic: the caller (a `projects/*` app) picks the Domain
and passes it in. Nothing here imports `projects.*`.
"""
from __future__ import annotations

import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import chatkit.config as config  # TODO(4.3): thread a real Settings object instead
from chatkit import events
from chatkit.app_config import build_app_config
from chatkit.chat import run_chat
from chatkit.domain import Domain
from chatkit.auth import router as auth_router
from chatkit.widgets import build_rest_router

_CHATKIT_FRONTEND = Path(__file__).parent / "frontend"

_PUBLIC = (
    "/login.html",
    "/auth/",
    "/favicon",
    "/healthz",
    "/api/app-config",
    "/_chatkit/",
    "/app.css",
)


class Turn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[Turn] = []


_SENTINEL = object()


def create_app(domain: Domain, *, settings=None) -> FastAPI:
    """Build a chatkit FastAPI app bound to ``domain``.

    ``settings`` is accepted for forward-compatibility (Task 4.3) but unused;
    configuration is still read from ``chatkit.config`` at call time.
    """
    app = FastAPI(title="Agent Chat Analytics")

    # 1. auth router
    app.include_router(auth_router.router)

    # 2. generated widget REST router
    prefix = domain.report_prefix()
    if prefix:
        app.include_router(
            build_rest_router(
                domain.widgets(),
                prefix=prefix,
                con_factory=domain.open_connection,
            )
        )

        # 3. /filters/options (subsumes the hand-written footwear route)
        def filter_options() -> dict:
            con = domain.open_connection()
            try:
                return domain.filter_options(con)
            finally:
                close = getattr(con, "close", None)
                if callable(close):
                    close()

        app.add_api_route(
            f"{prefix}/filters/options", filter_options, methods=["GET"]
        )

    # 4. core API
    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/app-config")
    def app_config() -> dict:
        return build_app_config(domain)

    @app.post("/api/chat")
    def chat(req: ChatRequest) -> StreamingResponse:
        q: "queue.Queue" = queue.Queue()

        def sink(event: events.Event) -> None:
            q.put(event)

        history = [t.model_dump() for t in req.history]

        def worker() -> None:
            try:
                run_chat(domain, req.message, sink, history=history)
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

    # 5. /_chatkit static assets (package-relative)
    app.mount(
        "/_chatkit",
        StaticFiles(directory=str(_CHATKIT_FRONTEND)),
        name="chatkit-assets",
    )

    # 6. domain web dir — LAST so it never shadows the API
    web_dir = Path(domain.web_dir())

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    if web_dir.exists():
        app.mount(
            "/", StaticFiles(directory=str(web_dir), html=True), name="frontend"
        )

    # --- middleware ------------------------------------------------------- #
    @app.middleware("http")
    async def auth_gate(request: Request, call_next):
        # TODO(4.3): read from `settings` instead of the config module
        if not config.AUTH_ENABLED:
            request.state.user = {"email": "dev@localhost", "name": "Dev"}
            return await call_next(request)

        path = request.url.path
        if path.startswith(_PUBLIC):
            return await call_next(request)

        user = request.session.get("user")
        if not user:
            wants_json = path.startswith("/api/") or "application/json" in (
                request.headers.get("accept", "")
            )
            if wants_json:
                return JSONResponse({"error": "auth required"}, status_code=401)
            return RedirectResponse("/login.html")

        request.state.user = user
        return await call_next(request)

    # added last -> outermost, so request.session exists before auth_gate runs
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SESSION_SECRET,
        max_age=config.SESSION_MAX_AGE,
        same_site="lax",
        https_only=config.AUTH_ENABLED,
    )

    return app
