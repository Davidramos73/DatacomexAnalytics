import json
from backend import events


def test_step_to_sse():
    line = events.to_sse(events.Step(label="sql.query", detail="SELECT 1"))
    assert line.startswith("event: step\n")
    assert line.endswith("\n\n")
    payload = json.loads(line.split("data: ", 1)[1].strip())
    assert payload == {"label": "sql.query", "detail": "SELECT 1"}


def test_chart_to_sse_roundtrips_spec():
    ev = events.Chart(
        title="T", meta="bar", spec={"mark": "bar"},
        data={"columns": ["a"], "rows": [[1]]},
    )
    payload = json.loads(events.to_sse(ev).split("data: ", 1)[1].strip())
    assert payload["spec"] == {"mark": "bar"}
    assert payload["data"]["rows"] == [[1]]


def test_done_type():
    assert events.Done(seconds=1.2).type == "done"
