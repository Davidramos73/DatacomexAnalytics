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

import backend.config as config
from backend import events
from backend.agents import orchestrator, orchestrator_footwear
from backend.routers import auth as auth_router
from backend.routers import reports

# indirection for tests; pick the chat domain at import time
orchestrator_run = (
    orchestrator_footwear.run
    if config.CHAT_DOMAIN == "footwear"
    else orchestrator.run
)

_FRONTEND = Path(__file__).parent.parent / "frontend"
_PUBLIC = ("/login.html", "/auth/", "/favicon", "/healthz")

app = FastAPI(title="Agent Chat Analytics")
app.include_router(auth_router.router)
app.include_router(reports.router)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    if not config.AUTH_ENABLED:
        request.state.user = {"email": "dev@localhost", "name": "Dev"}
        return await call_next(request)

    path = request.url.path
    if path.startswith(_PUBLIC):
        return await call_next(request)

    user = request.session.get("user")
    if not user:
        wants_json = path.startswith("/api/") or "application/json" in request.headers.get(
            "accept", ""
        )
        if wants_json:
            return JSONResponse({"error": "auth required"}, status_code=401)
        return RedirectResponse("/login.html")

    request.state.user = user
    return await call_next(request)


# added last -> outermost, so request.session is populated before auth_gate runs
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    max_age=config.SESSION_MAX_AGE,
    same_site="lax",
    https_only=config.AUTH_ENABLED,
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


class Turn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[Turn] = []


_SENTINEL = object()


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    q: "queue.Queue" = queue.Queue()

    def sink(event: events.Event) -> None:
        q.put(event)

    history = [t.model_dump() for t in req.history]

    def worker() -> None:
        try:
            orchestrator_run(req.message, sink, history=history)
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
