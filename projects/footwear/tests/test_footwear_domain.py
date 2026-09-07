from projects.footwear.domain import FootwearDomain


def test_app_config_has_reports_tab_and_prompts():
    cfg = FootwearDomain().app_config()
    assert cfg.branding.name == "Analista de Calzado"
    assert len(cfg.example_prompts) == 10
    tab = cfg.tabs[0]
    assert tab.kind == "widget_grid"
    assert "evolution" in tab.widgets


def test_step_label_is_spanish():
    s = FootwearDomain().step_label(
        "footwear_top_partners", {"flow": "IMPORT", "top_n": 5}
    )
    assert s.label == "Calculando el ranking de países"
    assert "Importación" in s.detail
