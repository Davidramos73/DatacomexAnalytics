"""Who uses the platform: a tiny SQLite users table + a session log.

stdlib sqlite3 (no dependency). One connection per call — cheap, and keeps
us out of thread-safety trouble.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import backend.config as config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email      TEXT PRIMARY KEY,
    name       TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    sessions   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS session_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL,
    at         TEXT NOT NULL,
    user_agent TEXT
);
"""


def _connect() -> sqlite3.Connection:
    config.AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.AUTH_DB_PATH)
    con.executescript(_SCHEMA)
    return con


def record_login(email: str, name: str, user_agent: str | None) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO users (email, name, first_seen, last_seen, sessions)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(email) DO UPDATE SET
                name = excluded.name,
                last_seen = excluded.last_seen,
                sessions = users.sessions + 1
            """,
            (email, name, now, now),
        )
        con.execute(
            "INSERT INTO session_log (email, at, user_agent) VALUES (?, ?, ?)",
            (email, now, user_agent),
        )
        con.commit()
    finally:
        con.close()
