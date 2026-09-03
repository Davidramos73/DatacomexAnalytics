import importlib

import pytest


@pytest.fixture(autouse=True)
def _reload_config_after():
    """These tests reload backend.config with tweaked env; put it back after."""
    yield
    import backend.config as config
    importlib.reload(config)


def test_defaults(monkeypatch):
    for var in ("LLM_MODEL", "DATA_AGENT_MODEL", "MAX_AGENT_ITERS", "SQL_MAX_ROWS"):
        monkeypatch.delenv(var, raising=False)
    import backend.config as config
    importlib.reload(config)
    assert config.LLM_MODEL == "claude-opus-5"
    assert config.DATA_AGENT_MODEL == "claude-opus-5"
    assert config.MAX_AGENT_ITERS == 6
    assert config.SQL_MAX_ROWS == 500
    assert config.MAX_TOKENS == 16000
    assert config.WAREHOUSE_PATH.name == "warehouse.duckdb"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("MAX_AGENT_ITERS", "3")
    import backend.config as config
    importlib.reload(config)
    assert config.LLM_MODEL == "claude-sonnet-5"
    assert config.DATA_AGENT_MODEL == "claude-sonnet-5"  # falls back to LLM_MODEL
    assert config.MAX_AGENT_ITERS == 3


def test_provider_defaults_to_anthropic(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "DATA_AGENT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    import backend.config as config
    importlib.reload(config)
    assert config.LLM_PROVIDER == "anthropic"
    assert config.LLM_MODEL == "claude-opus-5"


def test_openrouter_provider_switches_default_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("DATA_AGENT_MODEL", raising=False)
    import backend.config as config
    importlib.reload(config)
    assert config.LLM_PROVIDER == "openrouter"
    assert config.LLM_MODEL == "deepseek/deepseek-v4-pro-0813"
    assert config.OPENROUTER_BASE_URL.endswith("/api/v1")
