from __future__ import annotations

import queue
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import events
from backend.agents import orchestrator

orchestrator_run = orchestrator.run  # indirection for tests

_FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="Agent Chat Analytics")


class ChatRequest(BaseModel):
    session_id: str
    message: str


_SENTINEL = object()


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    q: "queue.Queue" = queue.Queue()

    def sink(event: events.Event) -> None:
        q.put(event)

    def worker() -> None:
        try:
            orchestrator_run(req.message, sink)
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
