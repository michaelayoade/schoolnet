from __future__ import annotations

from app.models.domain_settings import DomainSetting, SettingDomain, SettingValueType
from app.services.branding import generate_css, get_branding, save_branding


def test_get_branding_returns_defaults(db_session) -> None:
    branding = get_branding(db_session)
    assert branding["display_name"]
    assert branding["primary_color"].startswith("#")
    assert branding["accent_color"].startswith("#")


def test_save_branding_persists_values(db_session) -> None:
    save_branding(
        db_session,
        {
            "display_name": "Acme Starter",
            "primary_color": "#112233",
            "accent_color": "#445566",
            "font_family_display": "Outfit",
            "font_family_body": "Inter",
        },
    )
    branding = get_branding(db_session)
    assert branding["display_name"] == "Acme Starter"
    assert branding["primary_color"] == "#112233"
    assert branding["accent_color"] == "#445566"


def test_generate_css_contains_brand_variables() -> None:
    css = generate_css(
        {
            "primary_color": "#123456",
            "accent_color": "#ABCDEF",
            "font_family_display": "Outfit",
            "font_family_body": "Plus Jakarta Sans",
            "custom_css": ".demo { color: red; }",
        }
    )
    assert "--brand-primary: #123456;" in css
    assert "--brand-accent: #ABCDEF;" in css
    assert ".demo { color: red; }" in css


def test_save_branding_uses_branding_domain(db_session) -> None:
    save_branding(
        db_session,
        {
            "display_name": "Brand Domain Check",
        },
    )
    setting = (
        db_session.query(DomainSetting)
        .filter(DomainSetting.key == "ui_branding")
        .first()
    )
    assert setting is not None
    assert setting.domain == SettingDomain.branding


def test_get_branding_falls_back_to_legacy_scheduler_domain(db_session) -> None:
    legacy = DomainSetting(
        domain=SettingDomain.scheduler,
        key="ui_branding",
        value_type=SettingValueType.json,
        value_json={"display_name": "Legacy Branding"},
        is_active=True,
    )
    db_session.add(legacy)
    db_session.commit()

    branding = get_branding(db_session)
    assert branding["display_name"] == "Legacy Branding"
