import duckdb
import pytest
from backend.warehouse import schema, seed


@pytest.fixture
def con(tmp_path):
    db_path = tmp_path / "w.duckdb"
    seed.build(db_path)
    c = duckdb.connect(str(db_path), read_only=True)
    yield c
    c.close()


def test_introspect_lists_all_tables(con):
    text = schema.introspect(con)
    for table in seed.TABLES:
        assert table in text
    assert "net_revenue" in text


def test_schema_context_includes_notes_and_samples(con):
    ctx = schema.schema_context(con)
    assert schema.SCHEMA_NOTES.strip()[:20] in ctx
    assert "fct_orders" in ctx
    # sample rows section mentions a real region value
    assert "North America" in ctx
