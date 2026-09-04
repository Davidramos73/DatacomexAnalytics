import duckdb
import pytest

from backend.warehouse import datacomex_seed
from backend.warehouse.datacomex_schema import HEADINGS


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    p = tmp_path_factory.mktemp("dc") / "footwear.duckdb"
    datacomex_seed.build(p)
    c = duckdb.connect(str(p), read_only=True)
    yield c
    c.close()


def test_rows_are_deterministic():
    assert datacomex_seed._rows() == datacomex_seed._rows()


def test_tables_are_populated(con):
    for t in ("trade_flows", "taric_tree", "meta_ingestion"):
        (n,) = con.execute(f"SELECT COUNT(*) FROM datacomex.{t}").fetchone()
        assert n > 0, t


def test_both_flows_present(con):
    flows = {r[0] for r in con.execute(
        "SELECT DISTINCT flow FROM datacomex.trade_flows").fetchall()}
    assert flows == {"IMPORT", "EXPORT"}


def test_every_taric_code_exists_in_the_tree_at_level_6(con):
    (orphans,) = con.execute(
        "SELECT COUNT(*) FROM datacomex.trade_flows f "
        "LEFT JOIN datacomex.taric_tree t ON f.taric_code = t.code AND t.level = 6 "
        "WHERE t.code IS NULL"
    ).fetchone()
    assert orphans == 0


def test_tree_has_every_heading(con):
    headings = {r[0] for r in con.execute(
        "SELECT code FROM datacomex.taric_tree WHERE level = 4").fetchall()}
    assert headings == set(HEADINGS)


def test_parts_heading_has_no_supplementary_units(con):
    (n,) = con.execute(
        "SELECT COUNT(*) FROM datacomex.trade_flows "
        "WHERE heading = '6406' AND suppl_units IS NOT NULL"
    ).fetchone()
    assert n == 0


def test_only_the_latest_period_is_provisional(con):
    prov = {r[0] for r in con.execute(
        "SELECT DISTINCT period FROM datacomex.trade_flows WHERE is_provisional"
    ).fetchall()}
    (max_period,) = con.execute(
        "SELECT MAX(period) FROM datacomex.trade_flows").fetchone()
    assert prov == {max_period}
