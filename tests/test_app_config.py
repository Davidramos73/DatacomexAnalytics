import duckdb
import pytest
from fastapi.testclient import TestClient

import backend.config as config
from backend import app as app_module
from backend.warehouse.datacomex_schema import HEADINGS, SCHEMA_DDL


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "dc.duckdb"
    monkeypatch.setattr(config, "DATACOMEX_PATH", db_path)
    c = duckdb.connect(str(db_path))
    c.execute(SCHEMA_DDL)
    c.executemany(
        "INSERT INTO datacomex.taric_tree VALUES (?, ?, ?, ?)",
        [("64", None, 2, "Calzado")]
        + [(h, "64", 4, d) for h, (d, _) in HEADINGS.items()],
    )
    c.executemany(
        "INSERT INTO datacomex.trade_flows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("IMPORT", "2024-01", 2024, 1, "CHN", "China", "640411", "64", "6404",
             50_000_000, 4_000_000, None, False),
        ],
    )
    c.close()
    yield TestClient(app_module.app)


def test_app_config_public_and_shaped(client):
    r = client.get("/api/app-config")  # no auth
    assert r.status_code == 200
    body = r.json()
    assert body["branding"]["name"] == "Analista de Calzado"
    assert "reports" == body["tabs"][0]["id"]
    assert body["widgets"]["evolution"]["rest_path"].endswith("/evolution")
    assert body["widgets"]["evolution"]["rest_path"].startswith("/api/v1/reports/footwear")
    assert isinstance(body["example_prompts"], list) and body["example_prompts"]
