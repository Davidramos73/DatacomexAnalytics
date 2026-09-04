from backend.ingest.client import DataComexClient


def _fake_get(canned):
    calls = []

    def get(path, params):
        calls.append((path, dict(params)))
        return canned[path]

    return get, calls


def test_get_periods_hits_the_right_path():
    get, calls = _fake_get({"/ObtenerPeriodos": [{"CodPeriodo": "2023"}]})
    client = DataComexClient(token="t", get_fn=get)
    assert client.get_periods() == [{"CodPeriodo": "2023"}]
    assert calls == [("/ObtenerPeriodos", {})]


def test_get_taric_tree_hits_the_right_path():
    get, calls = _fake_get({"/ObtenerTarics": [{"Taric": "64"}]})
    client = DataComexClient(token="t", get_fn=get)
    assert client.get_taric_tree() == [{"Taric": "64"}]


def test_get_data_sends_expected_params_and_unwraps_resultados():
    get, calls = _fake_get({
        "/ObtenerDatos": {"Resultados": [{"taric": "6404"}]}
    })
    client = DataComexClient(token="t", get_fn=get)
    out = client.get_data(flow="I/E", period="202312", taric="H6404")
    assert out == [{"taric": "6404"}]
    assert calls == [
        ("/ObtenerDatos",
         {"f": "I/E", "pe": "202312", "pa": "ALL", "ta": "H6404", "pr": "TOTAL"})
    ]


def test_get_data_defaults_to_empty_list_when_no_resultados():
    get, calls = _fake_get({"/ObtenerDatos": {}})
    client = DataComexClient(token="t", get_fn=get)
    assert client.get_data(flow="I", period="202312", taric="64") == []
