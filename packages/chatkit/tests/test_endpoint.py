from fastapi.testclient import TestClient
from chatkit import app as app_module
from chatkit import events


def _fake_run(domain, message, sink, **kw):
    sink(events.Thinking(label="Reading schema"))
    sink(events.Step(label="sql.query", detail="SELECT 1"))
    sink(events.Text(text="hello"))
    sink(events.Chart(title="T", meta="bar", spec={"mark": "bar"},
                      data={"columns": ["a"], "rows": [[1]]}))
    sink(events.Done(seconds=0.1))


def test_chat_streams_events(monkeypatch):
    monkeypatch.setattr(app_module, "run_chat", _fake_run)
    client = TestClient(app_module.app)
    with client.stream("POST", "/api/chat",
                       json={"session_id": "s1", "message": "hi"}) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = "".join(r.iter_text())
    assert "event: thinking" in body
    assert "event: chart" in body
    assert body.strip().endswith("}")  # last event is 'done' with JSON payload
    assert "event: done" in body


def test_chat_forwards_history(monkeypatch):
    seen = {}

    def capture(domain, message, sink, **kw):
        seen["message"] = message
        seen["history"] = kw.get("history")
        sink(events.Done(seconds=0.0))

    monkeypatch.setattr(app_module, "run_chat", capture)
    client = TestClient(app_module.app)
    with client.stream("POST", "/api/chat", json={
        "session_id": "s1", "message": "follow up",
        "history": [
            {"role": "user", "content": "first q"},
            {"role": "assistant", "content": "first a"},
        ],
    }) as r:
        "".join(r.iter_text())
    assert seen["message"] == "follow up"
    assert seen["history"] == [
        {"role": "user", "content": "first q"},
        {"role": "assistant", "content": "first a"},
    ]


def test_chat_reports_errors(monkeypatch):
    def boom(domain, message, sink, **kw):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(app_module, "run_chat", boom)
    client = TestClient(app_module.app)
    with client.stream("POST", "/api/chat",
                       json={"session_id": "s", "message": "x"}) as r:
        body = "".join(r.iter_text())
    assert "event: error" in body
    assert "kaboom" in body
    assert "event: done" in body
