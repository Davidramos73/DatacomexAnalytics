"""DATACOMEX config bits (split out of the chatkit test_config)."""
import importlib

import pytest


@pytest.fixture(autouse=True)
def _reload_config_after():
    yield
    import chatkit.config as config
    importlib.reload(config)


def test_datacomex_path_default(monkeypatch):
    monkeypatch.delenv("DATACOMEX_PATH", raising=False)
    import chatkit.config as config
    importlib.reload(config)
    assert config.DATACOMEX_PATH.name == "footwear.duckdb"
    assert config.DATACOMEX_PATH.parent.name == "warehouse"


def test_datacomex_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DATACOMEX_PATH", str(tmp_path / "fw.duckdb"))
    import chatkit.config as config
    importlib.reload(config)
    assert config.DATACOMEX_PATH == tmp_path / "fw.duckdb"


def test_data_comex_token_default(monkeypatch):
    monkeypatch.delenv("DATA_COMEX_TOKEN", raising=False)
    import chatkit.config as config
    importlib.reload(config)
    assert config.DATA_COMEX_TOKEN == ""


def test_footwear_config_reexports():
    from projects.footwear import config as fw_config
    import chatkit.config as config
    assert fw_config.DATACOMEX_PATH == config.DATACOMEX_PATH
