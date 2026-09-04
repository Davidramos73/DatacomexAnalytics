import duckdb
import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.routers import reports
from backend.warehouse.datacomex_schema import HEADINGS, SCHEMA_DDL


@pytest.fixture
def client(tmp_path):
    c = duckdb.connect(str(tmp_path / "dc.duckdb"))
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
            ("IMPORT", "2024-02", 2024, 2, "CHN", "China", "640411", "64", "6404",
             60_000_000, 5_000_000, None, False),
            ("IMPORT", "2024-01", 2024, 1, "VNM", "Vietnam", "640411", "64", "6404",
             20_000_000, 2_000_000, None, False),
        ],
    )
    app_module.app.dependency_overrides[reports.get_footwear_con] = lambda: c
    yield TestClient(app_module.app)
    app_module.app.dependency_overrides.clear()
    c.close()


def test_evolution_endpoint(client):
    r = client.get(
        "/api/v1/reports/footwear/evolution", params={"flow": "import", "months": 12}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["widget"] == "monthly_evolution"
    assert body["echarts"]["series"][0]["data"] == [70.0, 60.0]  # (50+20), 60


def test_countries_endpoint(client):
    r = client.get(
        "/api/v1/reports/footwear/countries", params={"flow": "import", "top_n": 5}
    )
    assert r.status_code == 200
    assert r.json()["echarts"]["yAxis"]["data"] == ["Vietnam", "China"]


def test_filter_options_endpoint(client):
    r = client.get("/api/v1/reports/footwear/filters/options")
    assert r.status_code == 200
    assert r.json()["periods"] == ["2024-01", "2024-02"]


def test_product_mix_endpoint(client):
    r = client.get(
        "/api/v1/reports/footwear/product-mix", params={"flow": "import"}
    )
    assert r.status_code == 200
    assert r.json()["widget"] == "product_mix"
    assert r.json()["echarts"]["series"][0]["type"] == "pie"


def test_avg_price_endpoint(client):
    r = client.get(
        "/api/v1/reports/footwear/avg-price", params={"flow": "import", "months": 12}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["widget"] == "avg_price"
    # 2024-01: (50M + 20M) / (4M + 2M) kg = 11.67 €/kg ; 2024-02: 60/5 = 12.0
    assert body["echarts"]["series"][0]["data"] == [11.67, 12.0]


def test_balance_endpoint(client):
    r = client.get(
        "/api/v1/reports/footwear/balance", params={"months": 12}
    )
    assert r.status_code == 200
    assert r.json()["widget"] == "trade_balance"


def test_reports_page_is_served(client):
    r = client.get("/reportes.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
