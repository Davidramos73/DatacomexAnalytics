import os

from chatkit._demo.domain import DemoDomain


def test_demo_domain_is_usable():
    d = DemoDomain()
    cfg = d.app_config()
    assert cfg.branding.name
    assert isinstance(d.widgets(), list)
    assert d.system_prompt
    assert os.path.isdir(d.web_dir())
    assert os.path.isfile(os.path.join(d.web_dir(), "index.html"))
