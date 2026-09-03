import json

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


def test_non_json_values_are_coerced(con):
    out = db.run_sql(
        con, "SELECT CAST('2026-03-01' AS DATE) AS d, CAST(1.5 AS DECIMAL(4,2)) AS n"
    )
    json.dumps(out)  # must not raise
    d, n = out["rows"][0]
    assert isinstance(d, str) and d == "2026-03-01"
    assert isinstance(n, float) and n == 1.5


@pytest.mark.parametrize("bad", [
    "SELECT * FROM read_text('/etc/hostname')",
    "SELECT * FROM glob('/etc/*')",
])
def test_rejects_file_access(con, bad):
    with pytest.raises(db.UnsafeSQLError):
        db.run_sql(con, bad)


def test_query_timeout(con):
    with pytest.raises(db.UnsafeSQLError):
        db.run_sql(
            con,
            "SELECT count(*) FROM range(100000000000) t1, range(100000) t2",
            timeout_s=1,
        )
