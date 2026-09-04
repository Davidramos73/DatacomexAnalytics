import duckdb
import pytest

from backend.services import footwear
from backend.warehouse.datacomex_schema import HEADINGS, SCHEMA_DDL


@pytest.fixture
def con(tmp_path):
    """A tiny, fully-controlled DataComex warehouse."""
    c = duckdb.connect(str(tmp_path / "dc.duckdb"))
    c.execute(SCHEMA_DDL)
    c.executemany(
        "INSERT INTO datacomex.taric_tree VALUES (?, ?, ?, ?)",
        [("64", None, 2, "Calzado, polainas y artículos análogos")]
        + [(h, "64", 4, desc) for h, (desc, _) in HEADINGS.items()],
    )
    yield c
    c.close()


def _flow(**kw):
    base = dict(
        flow="IMPORT", period="2025-01", year=2025, month=1,
        country_code="CHN", country_name="China", taric_code="640411",
        chapter="64", heading="6404", value_eur=1_000_000, weight_kg=200_000,
        suppl_units=500_000, is_provisional=False,
    )
    base.update(kw)
    return tuple(base[k] for k in (
        "flow", "period", "year", "month", "country_code", "country_name",
        "taric_code", "chapter", "heading", "value_eur", "weight_kg",
        "suppl_units", "is_provisional",
    ))


def _insert(con, *rows):
    con.executemany(
        "INSERT INTO datacomex.trade_flows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        list(rows),
    )


# --------------------------------------------------------------------------- #
# resolve_taric
# --------------------------------------------------------------------------- #
def test_resolve_taric_maps_deportivas_to_textile_heading(con):
    assert footwear.resolve_taric(con, "zapatillas deportivas") == "6404"


def test_resolve_taric_maps_botas_de_agua_to_waterproof_heading(con):
    assert footwear.resolve_taric(con, "botas de agua") == "6401"


def test_resolve_taric_maps_cuero_to_leather_heading(con):
    assert footwear.resolve_taric(con, "botas de cuero") == "6403"


def test_resolve_taric_falls_back_to_description_match(con):
    assert footwear.resolve_taric(con, "polainas") == "6406"


def test_resolve_taric_unknown_returns_none(con):
    assert footwear.resolve_taric(con, "bufanda de lana") is None


# --------------------------------------------------------------------------- #
# evolution
# --------------------------------------------------------------------------- #
def test_evolution_returns_monthly_totals_in_millions(con):
    _insert(
        con,
        _flow(period="2024-10", year=2024, month=10, value_eur=10_000_000),
        _flow(period="2024-11", year=2024, month=11, value_eur=12_000_000),
        _flow(period="2024-12", year=2024, month=12, value_eur=15_500_000),
    )
    out = footwear.evolution(con, flow="IMPORT", heading="64", months=12)

    assert out["widget"] == "monthly_evolution"
    assert out["echarts"]["xAxis"]["data"] == ["2024-10", "2024-11", "2024-12"]
    series = out["echarts"]["series"][0]
    assert series["type"] == "line"
    assert series["data"] == [10.0, 12.0, 15.5]  # M€
    assert out["meta"]["unit"] == "EUR"


def test_evolution_yoy_kpi_is_percent_change(con):
    _insert(
        con,
        _flow(period="2023-06", year=2023, month=6, value_eur=100_000_000),
        _flow(period="2024-06", year=2024, month=6, value_eur=120_000_000),
    )
    out = footwear.evolution(con, flow="IMPORT", heading="64", months=24)
    kpi = next(k for k in out["kpis"] if "interanual" in k["label"].lower())
    assert kpi["value"] == "+20.0%"
    assert kpi["tone"] == "positive"


def test_evolution_filters_by_heading(con):
    _insert(
        con,
        _flow(period="2024-01", year=2024, month=1, heading="6404",
              taric_code="640411", value_eur=5_000_000),
        _flow(period="2024-01", year=2024, month=1, heading="6403",
              taric_code="640312", value_eur=99_000_000),
    )
    out = footwear.evolution(con, flow="IMPORT", heading="6404", months=12)
    assert out["echarts"]["series"][0]["data"] == [5.0]


def test_evolution_flags_provisional_periods(con):
    _insert(
        con,
        _flow(period="2024-11", year=2024, month=11, value_eur=1_000_000),
        _flow(period="2024-12", year=2024, month=12, value_eur=1_000_000,
              is_provisional=True),
    )
    out = footwear.evolution(con, flow="IMPORT", heading="64", months=12)
    assert out["meta"]["is_provisional"] is True


def test_evolution_accepts_bar_chart_type(con):
    _insert(con, _flow(value_eur=1_000_000))
    out = footwear.evolution(con, flow="IMPORT", chart_type="bar")
    assert out["echarts"]["series"][0]["type"] == "bar"


def test_evolution_falls_back_to_line_for_unknown_chart_type(con):
    _insert(con, _flow(value_eur=1_000_000))
    out = footwear.evolution(con, flow="IMPORT", chart_type="scatter")
    assert out["echarts"]["series"][0]["type"] == "line"


# --------------------------------------------------------------------------- #
# country_ranking
# --------------------------------------------------------------------------- #
def test_country_ranking_orders_by_value_and_reverses_for_horizontal_bar(con):
    _insert(
        con,
        _flow(country_code="CHN", country_name="China", value_eur=50_000_000),
        _flow(country_code="VNM", country_name="Vietnam", value_eur=30_000_000),
        _flow(country_code="ITA", country_name="Italia", value_eur=10_000_000),
    )
    out = footwear.country_ranking(con, flow="IMPORT", heading="64", top_n=2)

    assert out["widget"] == "country_ranking"
    # horizontal bar => #1 partner sits at the top of the y axis
    assert out["echarts"]["yAxis"]["data"] == ["Vietnam", "China"]
    assert out["echarts"]["series"][0]["data"] == [30.0, 50.0]


def test_country_ranking_respects_period_range(con):
    _insert(
        con,
        _flow(country_name="China", period="2024-01", year=2024, month=1,
              value_eur=99_000_000),
        _flow(country_name="China", period="2024-06", year=2024, month=6,
              value_eur=5_000_000),
    )
    out = footwear.country_ranking(
        con, flow="IMPORT", period_from="2024-05", period_to="2024-12"
    )
    assert out["echarts"]["series"][0]["data"] == [5.0]


def test_country_ranking_leader_share_kpi(con):
    _insert(
        con,
        _flow(country_code="CHN", country_name="China", value_eur=80_000_000),
        _flow(country_code="VNM", country_name="Vietnam", value_eur=20_000_000),
    )
    out = footwear.country_ranking(con, flow="IMPORT")
    kpi = next(k for k in out["kpis"] if "lider" in _ascii(k["label"]))
    assert kpi["value"] == "80.0%"


def test_country_ranking_accepts_pie_chart_type(con):
    _insert(
        con,
        _flow(country_code="CHN", country_name="China", value_eur=80_000_000),
        _flow(country_code="VNM", country_name="Vietnam", value_eur=20_000_000),
    )
    out = footwear.country_ranking(con, flow="IMPORT", chart_type="pie")
    series = out["echarts"]["series"][0]
    assert series["type"] == "pie"
    by_name = {d["name"]: d["value"] for d in series["data"]}
    assert by_name["China"] == 80.0


def test_country_ranking_falls_back_to_bar_for_unknown_chart_type(con):
    _insert(con, _flow(country_name="China", value_eur=80_000_000))
    out = footwear.country_ranking(con, flow="IMPORT", chart_type="line")
    assert out["echarts"]["series"][0]["type"] == "bar"


def _ascii(s: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c)
    )


# --------------------------------------------------------------------------- #
# filter_options
# --------------------------------------------------------------------------- #
def test_filter_options_lists_periods_headings_and_top_countries(con):
    _insert(
        con,
        _flow(country_code="CHN", country_name="China", period="2024-01",
              year=2024, month=1, value_eur=90_000_000),
        _flow(country_code="VNM", country_name="Vietnam", period="2024-02",
              year=2024, month=2, value_eur=10_000_000),
    )
    out = footwear.filter_options(con)

    assert out["periods"] == ["2024-01", "2024-02"]
    assert {h["code"] for h in out["headings"]} == {
        "6401", "6402", "6403", "6404", "6405", "6406"
    }
    assert out["headings"][0]["description"]  # non-empty label
    assert out["countries"][0] == "China"  # ordered by value desc


# --------------------------------------------------------------------------- #
# product_mix
# --------------------------------------------------------------------------- #
def test_product_mix_donut_by_heading(con):
    _insert(
        con,
        _flow(heading="6404", taric_code="640411", value_eur=60_000_000),
        _flow(heading="6403", taric_code="640312", value_eur=30_000_000),
        _flow(heading="6402", taric_code="640212", value_eur=10_000_000),
    )
    out = footwear.product_mix(con, flow="IMPORT")

    assert out["widget"] == "product_mix"
    series = out["echarts"]["series"][0]
    assert series["type"] == "pie"
    by_name = {d["name"]: d["value"] for d in series["data"]}
    assert by_name["6404 · textil"] == 60.0
    assert by_name["6403 · cuero"] == 30.0
    kpi = next(k for k in out["kpis"] if "cuota" in _ascii(k["label"]))
    assert kpi["value"] == "60.0%"  # dominant heading


def test_product_mix_accepts_bar_chart_type(con):
    _insert(con, _flow(heading="6404", taric_code="640411", value_eur=60_000_000))
    out = footwear.product_mix(con, flow="IMPORT", chart_type="bar")
    series = out["echarts"]["series"][0]
    assert series["type"] == "bar"
    assert series["data"] == [60.0]


def test_product_mix_falls_back_to_pie_for_unknown_chart_type(con):
    _insert(con, _flow(heading="6404", taric_code="640411", value_eur=60_000_000))
    out = footwear.product_mix(con, flow="IMPORT", chart_type="line")
    assert out["echarts"]["series"][0]["type"] == "pie"


# --------------------------------------------------------------------------- #
# avg_price
# --------------------------------------------------------------------------- #
def test_avg_price_is_value_over_weight_per_period(con):
    _insert(
        con,
        _flow(period="2024-01", year=2024, month=1,
              value_eur=20_000_000, weight_kg=1_000_000),   # 20 €/kg
        _flow(period="2024-02", year=2024, month=2,
              value_eur=30_000_000, weight_kg=1_000_000),   # 30 €/kg
    )
    out = footwear.avg_price(con, flow="IMPORT", months=12)

    assert out["widget"] == "avg_price"
    assert out["echarts"]["series"][0]["data"] == [20.0, 30.0]
    assert out["echarts"]["yAxis"]["name"] == "€/kg"


def test_avg_price_guards_against_zero_weight(con):
    _insert(
        con,
        _flow(period="2024-01", year=2024, month=1,
              value_eur=5_000_000, weight_kg=0),
    )
    out = footwear.avg_price(con, flow="IMPORT", months=12)
    assert out["echarts"]["series"][0]["data"] == [None]


def test_avg_price_accepts_bar_chart_type(con):
    _insert(con, _flow(value_eur=20_000_000, weight_kg=1_000_000))
    out = footwear.avg_price(con, flow="IMPORT", chart_type="bar")
    assert out["echarts"]["series"][0]["type"] == "bar"


def test_avg_price_falls_back_to_line_for_unknown_chart_type(con):
    _insert(con, _flow(value_eur=20_000_000, weight_kg=1_000_000))
    out = footwear.avg_price(con, flow="IMPORT", chart_type="pie")
    assert out["echarts"]["series"][0]["type"] == "line"


# --------------------------------------------------------------------------- #
# balance
# --------------------------------------------------------------------------- #
def test_balance_monthly_saldo_and_cumulative(con):
    _insert(
        con,
        _flow(flow="EXPORT", period="2024-01", year=2024, month=1, value_eur=30_000_000),
        _flow(flow="IMPORT", period="2024-01", year=2024, month=1, value_eur=10_000_000),
        _flow(flow="EXPORT", period="2024-02", year=2024, month=2, value_eur=5_000_000),
        _flow(flow="IMPORT", period="2024-02", year=2024, month=2, value_eur=25_000_000),
    )
    out = footwear.balance(con, months=12)

    assert out["widget"] == "trade_balance"
    series = {s["name"]: s["data"] for s in out["echarts"]["series"]}
    assert series["Saldo"] == [20.0, -20.0]          # 30-10, 5-25
    assert series["Acumulado"] == [20.0, 0.0]        # running sum
    assert {s["type"] for s in out["echarts"]["series"]} == {"bar", "line"}


def test_balance_saldo_accepts_line_chart_type(con):
    _insert(
        con,
        _flow(flow="EXPORT", period="2024-01", year=2024, month=1, value_eur=30_000_000),
        _flow(flow="IMPORT", period="2024-01", year=2024, month=1, value_eur=10_000_000),
    )
    out = footwear.balance(con, chart_type="line")
    series = {s["name"]: s["type"] for s in out["echarts"]["series"]}
    assert series["Saldo"] == "line"
    assert series["Acumulado"] == "line"


def test_balance_falls_back_to_bar_for_unknown_chart_type(con):
    _insert(
        con,
        _flow(flow="EXPORT", period="2024-01", year=2024, month=1, value_eur=30_000_000),
        _flow(flow="IMPORT", period="2024-01", year=2024, month=1, value_eur=10_000_000),
    )
    out = footwear.balance(con, chart_type="pie")
    series = {s["name"]: s["type"] for s in out["echarts"]["series"]}
    assert series["Saldo"] == "bar"
