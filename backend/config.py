import os
from pathlib import Path

# "anthropic" (default) uses the Anthropic Messages API; "openrouter" and
# "deepseek" use the OpenAI-compatible chat-completions API (OpenRouter's
# aggregator, or DeepSeek's own endpoint).
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()

# "footwear" routes /api/chat through the DataComex footwear orchestrator
# (typed report tools); "analytics" uses the free-SQL demo warehouse.
CHAT_DOMAIN = os.environ.get("CHAT_DOMAIN", "footwear").lower()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

_DEFAULT_MODEL = {
    "openrouter": "deepseek/deepseek-v4-pro-0813",
    # NB: the `deepseek-chat` alias currently resolves to V4 Flash (weak);
    # name the Pro model explicitly.
    "deepseek": "deepseek-v4-pro",
}.get(LLM_PROVIDER, "claude-opus-5")
LLM_MODEL = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
DATA_AGENT_MODEL = os.environ.get("DATA_AGENT_MODEL", LLM_MODEL)

# Reasoning budget for OpenAI-compatible providers: "low" | "medium" | "high"
# (empty string = don't send the param). DeepSeek V4 burns a lot of thinking
# tokens by default; "low" is plenty for SQL + chart choices.
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "low")

MAX_AGENT_ITERS = int(os.environ.get("MAX_AGENT_ITERS", "6"))
SQL_MAX_ROWS = int(os.environ.get("SQL_MAX_ROWS", "500"))
SQL_TIMEOUT_S = float(os.environ.get("SQL_TIMEOUT_S", "10"))
MAX_TOKENS = 16000
RANDOM_SEED = 42

# --- auth (Google login) ---------------------------------------------------- #
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-insecure-secret")
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", str(60 * 60 * 24 * 14)))
ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}
AUTH_DB_PATH = Path(
    os.environ.get(
        "AUTH_DB_PATH",
        str(Path(__file__).parent / "warehouse" / "auth.sqlite"),
    )
)

WAREHOUSE_PATH = Path(
    os.environ.get(
        "WAREHOUSE_PATH",
        str(Path(__file__).parent / "warehouse" / "warehouse.duckdb"),
    )
)
