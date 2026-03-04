from __future__ import annotations

from pathlib import Path

from app.templates import templates


def _render(snippet: str, **context) -> str:
    wrapped = "{% autoescape true %}" + snippet + "{% endautoescape %}"
    return templates.env.from_string(wrapped).render(**context)


def test_sortable_th_renders_expected_query_params() -> None:
    html = _render(
        """
{% from "components/macros.html" import sortable_th %}
<table><thead><tr>{{ sortable_th("Email", "email", "email", "desc", "/", {"page": 2}) }}</tr></thead></table>
"""
    )
    assert "sort=email" in html
    assert "dir=asc" in html
    assert "page=2" in html


def test_status_badge_renders_status_text() -> None:
    html = _render(
        """
{% from "components/macros.html" import status_badge %}
{{ status_badge("active") }}
"""
    )
    assert "Active" in html


def test_branding_form_contains_csrf_hidden_input() -> None:
    template_path = Path("templates/branding.html")
    contents = template_path.read_text(encoding="utf-8")
    assert "csrf_form" in contents or 'name="csrf_token"' in contents


def test_admin_detail_templates_do_not_use_tojson_safe_in_pre() -> None:
    audit = Path("templates/admin/audit/detail.html").read_text(encoding="utf-8")
    webhook = Path("templates/admin/billing/webhook_events/detail.html").read_text(
        encoding="utf-8"
    )
    assert "| tojson(indent=2) | safe" not in audit
    assert "| tojson(indent=2) | safe" not in webhook
