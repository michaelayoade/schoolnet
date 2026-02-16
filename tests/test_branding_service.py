from __future__ import annotations

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
