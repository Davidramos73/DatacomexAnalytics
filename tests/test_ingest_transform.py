import pytest

from backend.ingest import transform


def test_parse_number_handles_comma_decimal():
    assert transform.parse_number("373198209,08") == pytest.approx(373198209.08)


def test_parse_number_handles_zero_and_none():
    assert transform.parse_number("0") == 0.0
    assert transform.parse_number(None) == 0.0


def test_heading_of_takes_first_four_digits():
    assert transform.heading_of("640411") == "6404"
    assert transform.heading_of("6404") == "6404"


def test_is_provisional_from_mensaje():
    assert transform.is_provisional("dato provisional") is True
    assert transform.is_provisional("dato definitivo") is False
    assert transform.is_provisional(None) is False


def test_row_to_tuple_maps_api_row_to_trade_flows_columns():
    api_row = {
        "flujo": "Importación", "pais": "Francia", "id_pais": "001",
        "taric": "640411", "euros": "1234,50", "kilos": "500,0",
        "mensaje": "dato definitivo",
    }
    out = transform.row_to_tuple(api_row, flow="IMPORT", period="2023-12",
                                  year=2023, month=12)
    assert out == (
        "IMPORT", "2023-12", 2023, 12, "001", "Francia", "640411",
        "64", "6404", 1234.5, 500.0, None, False,
    )


def test_row_to_tuple_reads_provisional_flag():
    api_row = {"flujo": "Exportación", "pais": "Italia", "id_pais": "005",
               "taric": "6403", "euros": "10", "kilos": "1",
               "mensaje": "dato provisional"}
    out = transform.row_to_tuple(api_row, flow="EXPORT", period="2026-06",
                                  year=2026, month=6)
    assert out[-1] is True


def test_flow_of_maps_spanish_labels():
    assert transform.flow_of("Importación") == "IMPORT"
    assert transform.flow_of("Exportación") == "EXPORT"


def test_period_label_converts_datacomex_month_code():
    assert transform.period_label("202312") == ("2023-12", 2023, 12)
    assert transform.period_label("202601") == ("2026-01", 2026, 1)
