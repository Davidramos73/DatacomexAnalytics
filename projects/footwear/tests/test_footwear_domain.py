from projects.footwear.domain import FootwearDomain


def test_app_config_has_reports_tab_and_prompts():
    cfg = FootwearDomain().app_config()
    assert cfg.branding.name == "Analista de Calzado"
    assert len(cfg.example_prompts) == 13
    tab = cfg.tabs[0]
    assert tab.kind == "widget_grid"
    assert "evolution" in tab.widgets
    components_tab = next(t for t in cfg.tabs if t.id == "components")
    assert "component_evolution" in components_tab.widgets


def test_step_label_is_spanish():
    s = FootwearDomain().step_label(
        "footwear_top_partners", {"flow": "IMPORT", "top_n": 5}
    )
    assert s.label == "Calculando el ranking de países"
    assert "Importación" in s.detail
