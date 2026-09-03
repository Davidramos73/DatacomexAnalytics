import os
from pathlib import Path

LLM_MODEL = os.environ.get("LLM_MODEL", "claude-opus-5")
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
