import pytest
from backend.warehouse import db, seed


@pytest.fixture
def con(tmp_path):
    p = tmp_path / "w.duckdb"
    seed.build(p)
    c = db.connect(p)
    yield c
    c.close()


def test_select_returns_structured_result(con):
    out = db.run_sql(con, "SELECT region, SUM(net_revenue) AS rev FROM fct_orders GROUP BY 1")
    assert out["columns"] == ["region", "rev"]
    assert out["row_count"] == len(out["rows"])
    assert out["truncated"] is False


@pytest.mark.parametrize("bad", [
    "DELETE FROM fct_orders",
    "UPDATE fct_orders SET net_revenue = 0",
    "DROP TABLE fct_orders",
    "SELECT 1; SELECT 2",
    "INSERT INTO dim_region VALUES ('x', 'y')",
    "ATTACH 'evil.db'",
])
def test_rejects_unsafe_sql(con, bad):
    with pytest.raises(db.UnsafeSQLError):
        db.run_sql(con, bad)


def test_with_cte_is_allowed(con):
    out = db.run_sql(con, "WITH t AS (SELECT 1 AS x) SELECT * FROM t")
    assert out["rows"] == [[1]]


def test_limit_is_injected_and_truncation_flagged(con):
    out = db.run_sql(con, "SELECT * FROM fct_orders", max_rows=5)
    assert out["row_count"] == 5
    assert out["truncated"] is True


def test_explicit_limit_is_respected(con):
    out = db.run_sql(con, "SELECT * FROM fct_orders LIMIT 3", max_rows=5)
    assert out["row_count"] == 3
    assert out["truncated"] is False
