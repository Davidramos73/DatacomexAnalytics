import duckdb
import pytest
from fastapi.testclient import TestClient

import chatkit.config as config
from chatkit import app as app_module
from projects.footwear.warehouse.schema import HEADINGS, SCHEMA_DDL


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


def test_app_config_pins_downstream_shape(client):
    body = client.get("/api/app-config").json()

    fopts = body["filter_options"]
    assert set(fopts) == {"periods", "headings", "countries"}
    assert fopts["periods"] == ["2024-01"]
    assert fopts["countries"] == ["China"]

    assert set(body["auth"]) == {"client_id", "enabled"}

    tab = body["tabs"][0]
    assert "widgets" in tab and "filters" in tab

    params = body["widgets"]["evolution"]["params"]
    assert isinstance(params, list)
    assert all(p["name"] != "chart_type" for p in params)


def test_app_config_carries_ui_copy(client):
    copy = client.get("/api/app-config").json()["copy"]
    assert copy["empty_title"] == "¿Qué miramos del calzado?"
    assert copy["placeholder"] == "Pregunta sobre el calzado…"
    assert copy["empty_text"].startswith("Pregunta por importaciones")
    # the tab link must stay wired through boot's data-role anchor
    assert 'data-role="hint-tab"' in copy["hint_html"]
    assert "DataComex (cap. 64, calzado)" in copy["hint_html"]


def test_app_config_months_carries_ui_bounds(client):
    params = client.get("/api/app-config").json()["widgets"]["evolution"]["params"]
    months = next(p for p in params if p["name"] == "months")
    assert months["ui_min"] == 6
    assert months["ui_max"] == 36
    heading = next(p for p in params if p["name"] == "heading")
    assert heading["ui_default_label"] == "Todo el calzado (cap. 64)"
