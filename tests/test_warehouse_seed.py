import duckdb
from backend.warehouse import seed


def test_build_creates_tables(tmp_path):
    db_path = tmp_path / "w.duckdb"
    seed.build(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for table in seed.TABLES:
            (count,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert count > 0, f"{table} is empty"
        # fct_orders has the columns the agents rely on
        cols = {r[0] for r in con.execute("DESCRIBE fct_orders").fetchall()}
        assert {"quarter", "region", "channel", "segment", "net_revenue"} <= cols
        # quarter values look like '2026Q3'
        quarters = {r[0] for r in con.execute("SELECT DISTINCT quarter FROM fct_orders").fetchall()}
        assert "2026Q3" in quarters
    finally:
        con.close()


def test_build_is_idempotent(tmp_path):
    db_path = tmp_path / "w.duckdb"
    seed.build(db_path)
    seed.build(db_path)  # must not raise
    con = duckdb.connect(str(db_path), read_only=True)
    (count,) = con.execute("SELECT COUNT(*) FROM fct_orders").fetchone()
    con.close()
    assert count > 0
