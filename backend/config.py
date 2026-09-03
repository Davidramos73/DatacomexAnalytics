import os
from pathlib import Path

# "anthropic" (default) uses the Anthropic Messages API; "openrouter" uses the
# OpenAI-compatible chat-completions API at OpenRouter.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)

_DEFAULT_MODEL = (
    "deepseek/deepseek-v4-pro-0813"
    if LLM_PROVIDER == "openrouter"
    else "claude-opus-5"
)
LLM_MODEL = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
DATA_AGENT_MODEL = os.environ.get("DATA_AGENT_MODEL", LLM_MODEL)

MAX_AGENT_ITERS = int(os.environ.get("MAX_AGENT_ITERS", "6"))
SQL_MAX_ROWS = int(os.environ.get("SQL_MAX_ROWS", "500"))
SQL_TIMEOUT_S = float(os.environ.get("SQL_TIMEOUT_S", "10"))
MAX_TOKENS = 16000
RANDOM_SEED = 42

WAREHOUSE_PATH = Path(
    os.environ.get(
        "WAREHOUSE_PATH",
        str(Path(__file__).parent / "warehouse" / "warehouse.duckdb"),
    )
)
