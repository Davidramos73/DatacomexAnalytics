import duckdb

from backend.ingest import build_warehouse


class _FakeClient:
    def __init__(self, periods, tree, data_by_period):
        self._periods = periods
        self._tree = tree
        self._data = data_by_period
        self.calls = []

    def get_periods(self):
        return self._periods

    def get_taric_tree(self):
        return self._tree

    def get_data(self, *, flow, period, taric, pais="ALL", provincia="TOTAL"):
        self.calls.append(period)
        return self._data.get(period, [])


TREE = [
    {"Taric": "64", "TaricPadre": "", "Nombre": "64 CALZADO; SUS PARTES", "Nivel": "1"},
    {"Taric": "6404", "TaricPadre": "64", "Nombre": "6404 Calzado textil", "Nivel": "2"},
    {"Taric": "640411", "TaricPadre": "6404", "Nombre": "640411 detalle", "Nivel": "3"},
    {"Taric": "64CC", "TaricPadre": "64", "Nombre": "64CC Correcciones", "Nivel": "2"},  # non-numeric, skip
]

PERIODS = [
    {"CodPeriodo": "2023", "Nivel": "1"},       # yearly - skipped
    {"CodPeriodo": "202301", "Nivel": "2"},
    {"CodPeriodo": "202312", "Nivel": "2"},
    {"CodPeriodo": "202212", "Nivel": "2"},     # before from_year - skipped
]

DATA = {
    "202312": [{"flujo": "Importación", "pais": "Francia", "id_pais": "001",
                "taric": "640411", "euros": "100", "kilos": "10",
                "mensaje": "dato definitivo"}],
    "202301": [{"flujo": "Exportación", "pais": "Italia", "id_pais": "005",
                "taric": "640411", "euros": "50", "kilos": "5",
                "mensaje": "dato provisional"}],
}


def test_requests_periods_newest_first_within_range(tmp_path):
    client = _FakeClient(PERIODS, TREE, DATA)
    build_warehouse.build(path=tmp_path / "real.duckdb", client=client, from_year=2023)
    assert client.calls == ["202312", "202301"]


def test_build_writes_taric_tree_and_trade_flows(tmp_path):
    client = _FakeClient(PERIODS, TREE, DATA)
    path = tmp_path / "real.duckdb"

    build_warehouse.build(path=path, client=client, from_year=2023)

    con = duckdb.connect(str(path), read_only=True)
    try:
        # only numeric taric codes make it into the tree
        codes = {r[0] for r in con.execute(
            "SELECT code FROM datacomex.taric_tree").fetchall()}
        assert codes == {"64", "6404", "640411"}
        assert con.execute(
            "SELECT level FROM datacomex.taric_tree WHERE code='640411'"
        ).fetchone()[0] == 6

        rows = con.execute(
            "SELECT flow, period, country_name, value_eur, weight_kg, is_provisional "
            "FROM datacomex.trade_flows ORDER BY period"
        ).fetchall()
        assert rows == [
            ("EXPORT", "2023-01", "Italia", 50.0, 5.0, True),
            ("IMPORT", "2023-12", "Francia", 100.0, 10.0, False),
        ]

        meta = con.execute(
            "SELECT source, rows_loaded, period_max FROM datacomex.meta_ingestion"
        ).fetchone()
        assert meta == ("api", 2, "202312")
    finally:
        con.close()


def test_build_is_resumable_by_overwriting_the_target(tmp_path):
    client = _FakeClient(PERIODS, TREE, DATA)
    path = tmp_path / "real.duckdb"
    build_warehouse.build(path=path, client=client, from_year=2023)
    build_warehouse.build(path=path, client=client, from_year=2023)  # must not crash

    con = duckdb.connect(str(path), read_only=True)
    (n,) = con.execute("SELECT COUNT(*) FROM datacomex.trade_flows").fetchone()
    con.close()
    assert n == 2  # not doubled
