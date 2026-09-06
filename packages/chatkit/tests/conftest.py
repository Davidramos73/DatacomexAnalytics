import importlib
import pytest


@pytest.fixture(scope="session", autouse=True)
def _quiet_anthropic_key(tmp_path_factory):
    # Ensure unit tests never accidentally hit the real API without a key set.
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-not-a-real-key")
    yield
