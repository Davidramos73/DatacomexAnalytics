import duckdb
import pytest

from projects.footwear.services import components
from projects.footwear.warehouse.schema import SCHEMA_DDL


@pytest.fixture
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "dc.duckdb"))
    c.execute(SCHEMA_DDL)
    yield c
    c.close()


def _flow(**kw):
    base = dict(
        flow="IMPORT", period="2025-01", year=2025, month=1,
        country_code="CHN", country_name="China", partida="40011000",
        value_eur=1_000_000, weight_kg=50_000, is_provisional=False,
    )
    base.update(kw)
    return tuple(base[k] for k in (
        "flow", "period", "year", "month", "country_code", "country_name",
        "partida", "value_eur", "weight_kg", "is_provisional",
    ))


def _insert(con, *rows):
    con.executemany(
        "INSERT INTO datacomex.component_flows VALUES (?,?,?,?,?,?,?,?,?,?)",
        list(rows),
    )


# --------------------------------------------------------------------------- #
# evolution
# --------------------------------------------------------------------------- #
def test_evolution_aggregates_all_partidas_by_default(con):
    _insert(
        con,
        _flow(partida="40011000", period="2025-01", month=1, value_eur=1_000_000),
        _flow(partida="41120000", period="2025-01", month=1, value_eur=500_000),
    )
    out = components.evolution(con, flow="IMPORT")
    assert out["echarts"]["series"][0]["data"] == [1.5]


def test_evolution_scopes_to_one_partida(con):
    _insert(
        con,
        _flow(partida="40011000", period="2025-01", month=1, value_eur=1_000_000),
        _flow(partida="41120000", period="2025-01", month=1, value_eur=500_000),
    )
    out = components.evolution(con, flow="IMPORT", partida="40011000")
    assert out["echarts"]["series"][0]["data"] == [1.0]


def test_evolution_no_data_returns_empty_series(con):
    out = components.evolution(con, flow="EXPORT")
    assert out["echarts"]["series"][0]["data"] == []


def test_evolution_flags_provisional(con):
    _insert(con, _flow(is_provisional=True))
    out = components.evolution(con, flow="IMPORT")
    assert "incluye datos provisionales" in out["meta"]["notes"]


# --------------------------------------------------------------------------- #
# country_ranking
# --------------------------------------------------------------------------- #
def test_country_ranking_orders_by_value_desc(con):
    _insert(
        con,
        _flow(country_name="China", value_eur=3_000_000),
        _flow(country_name="Italia", value_eur=1_000_000),
    )
    out = components.country_ranking(con, flow="IMPORT")
    # horizontal bar categories are reversed (leader last)
    assert out["echarts"]["yAxis"]["data"][-1] == "China"


def test_country_ranking_leader_share_kpi(con):
    _insert(
        con,
        _flow(country_name="China", value_eur=3_000_000),
        _flow(country_name="Italia", value_eur=1_000_000),
    )
    out = components.country_ranking(con, flow="IMPORT")
    assert out["kpis"][0]["value"] == "75.0%"


def test_country_ranking_high_concentration_flags_negative_tone(con):
    _insert(con, _flow(country_name="China", value_eur=1_000_000))
    out = components.country_ranking(con, flow="IMPORT")
    assert out["kpis"][0]["tone"] == "negative"


def test_country_ranking_pie_chart_type(con):
    _insert(con, _flow())
    out = components.country_ranking(con, flow="IMPORT", chart_type="pie")
    assert out["echarts"]["series"][0]["type"] == "pie"


# --------------------------------------------------------------------------- #
# balance
# --------------------------------------------------------------------------- #
def test_balance_export_minus_import(con):
    _insert(
        con,
        _flow(flow="EXPORT", value_eur=3_000_000),
        _flow(flow="IMPORT", value_eur=1_000_000),
    )
    out = components.balance(con)
    assert out["echarts"]["series"][0]["data"] == [2.0]


def test_balance_scopes_to_one_partida(con):
    _insert(
        con,
        _flow(flow="EXPORT", partida="40011000", value_eur=1_000_000),
        _flow(flow="EXPORT", partida="41120000", value_eur=5_000_000),
    )
    out = components.balance(con, partida="40011000")
    assert out["echarts"]["series"][0]["data"] == [1.0]


def test_balance_positive_total_is_positive_tone(con):
    _insert(con, _flow(flow="EXPORT", value_eur=1_000_000))
    out = components.balance(con)
    assert out["kpis"][0]["tone"] == "positive"


# --------------------------------------------------------------------------- #
# filter_options
# --------------------------------------------------------------------------- #
def test_filter_options_lists_all_70_partidas(con):
    out = components.filter_options(con)
    assert len(out["partidas"]) == 70
    assert all("code" in p and "description" in p for p in out["partidas"])
