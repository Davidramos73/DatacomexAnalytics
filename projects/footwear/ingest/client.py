"""Thin HTTP client for the DataComex API.

`get_fn(path, params) -> parsed_json` is injectable so tests never touch the
network; the default implementation uses `requests` with the bearer token.
"""
from __future__ import annotations

from typing import Callable

BASE_URL = "https://comercio.serviciosmin.gob.es/DatacomexApi"


class DataComexClient:
    def __init__(
        self,
        token: str,
        base_url: str = BASE_URL,
        get_fn: Callable[[str, dict], object] | None = None,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._get = get_fn or self._http_get

    def _http_get(self, path: str, params: dict):
        import requests

        resp = requests.get(
            self.base_url + path,
            params=params,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def get_periods(self) -> list[dict]:
        return self._get("/ObtenerPeriodos", {})

    def get_taric_tree(self) -> list[dict]:
        return self._get("/ObtenerTarics", {})

    def get_data(
        self,
        *,
        flow: str,
        period: str,
        taric: str,
        pais: str = "ALL",
        provincia: str = "TOTAL",
    ) -> list[dict]:
        data = self._get(
            "/ObtenerDatos",
            {"f": flow, "pe": period, "pa": pais, "ta": taric, "pr": provincia},
        )
        return (data or {}).get("Resultados", [])
