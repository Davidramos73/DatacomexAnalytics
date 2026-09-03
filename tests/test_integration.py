import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-"),
    reason="needs a real ANTHROPIC_API_KEY",
)


def test_end_to_end_revenue_by_region(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_PATH", str(tmp_path / "w.duckdb"))
    import importlib
    from backend import config
    importlib.reload(config)
    from backend.warehouse import seed
    seed.build()

    from backend import events
    from backend.agents import orchestrator
    importlib.reload(orchestrator)

    seen = []
    orchestrator.run("How did Q3 revenue break down by region? Chart it.", seen.append)

    kinds = [e.type for e in seen]
    assert "chart" in kinds, kinds
    chart = next(e for e in seen if isinstance(e, events.Chart))
    assert chart.spec["series"]
    assert chart.spec["dataset"]["source"]
