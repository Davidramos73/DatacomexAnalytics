"""DemoDomain - the in-package fixture domain.

Exists so chatkit's own tests and `create_app()` smoke checks never need to
import `projects.*`. It is SqlDomain over the demo warehouse, with its own
minimal web dir.
"""
from __future__ import annotations

from pathlib import Path

from chatkit.sql_domain import SqlDomain


class DemoDomain(SqlDomain):
    def web_dir(self) -> str:
        return str(Path(__file__).parent / "web")
