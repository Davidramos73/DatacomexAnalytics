from __future__ import annotations

import dataclasses

import backend.config as config
from backend.domain import Domain
from backend.widgets import widget_descriptors


def dataclass_to_dict(t) -> dict:
    return {k: v for k, v in dataclasses.asdict(t).items() if v is not None}


def build_app_config(domain: Domain) -> dict:
    cfg = domain.app_config()
    prefix = domain.report_prefix() or ""
    descs = widget_descriptors(domain.widgets())
    for d in descs.values():
        d["rest_path"] = prefix + d["rest_path"]

    if domain.report_prefix():
        con = domain.open_connection()
        try:
            fopts = domain.filter_options(con)
        finally:
            close = getattr(con, "close", None)
            if callable(close):
                close()
    else:
        fopts = {}

    return {
        "branding": {
            "name": cfg.branding.name,
            "short_name": cfg.branding.short_name,
            "badge": cfg.branding.badge,
            "favicon": cfg.branding.favicon,
        },
        "auth": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "enabled": config.AUTH_ENABLED,
        },
        "example_prompts": list(cfg.example_prompts),
        "echarts_themes": list(cfg.echarts_themes),
        "tabs": [dataclass_to_dict(t) for t in cfg.tabs],
        "widgets": descs,
        "filter_options": fopts,
    }
