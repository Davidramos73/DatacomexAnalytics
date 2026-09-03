from fastapi.testclient import TestClient
from backend import app as app_module
from backend import events


def _fake_run(message, sink, **kw):
    sink(events.Thinking(label="Reading schema"))
    sink(events.Step(label="sql.query", detail="SELECT 1"))
    sink(events.Text(text="hello"))
    sink(events.Chart(title="T", meta="bar", spec={"mark": "bar"},
                      data={"columns": ["a"], "rows": [[1]]}))
    sink(events.Done(seconds=0.1))


def test_chat_streams_events(monkeypatch):
    monkeypatch.setattr(app_module, "orchestrator_run", _fake_run)
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


def test_chat_reports_errors(monkeypatch):
    def boom(message, sink, **kw):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(app_module, "orchestrator_run", boom)
    client = TestClient(app_module.app)
    with client.stream("POST", "/api/chat",
                       json={"session_id": "s", "message": "x"}) as r:
        body = "".join(r.iter_text())
    assert "event: error" in body
    assert "kaboom" in body
    assert "event: done" in body
