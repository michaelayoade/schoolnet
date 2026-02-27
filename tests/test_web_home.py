from app.services.branding import get_branding


def test_branding_settings_requires_auth(client):
    response = client.get("/settings/branding", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/admin/login?next=/settings/branding"


def test_branding_settings_update_sanitizes_custom_css(
    client, db_session, person, auth_session, auth_token
):
    csrf_resp = client.get("/")
    csrf_token = csrf_resp.cookies.get("csrf_token", "")

    response = client.post(
        "/settings/branding",
        data={
            "display_name": "Secure Brand",
            "custom_css": "body{color:red;} </style> <script>alert(1)</script>",
        },
        headers={"X-CSRF-Token": csrf_token},
        cookies={"csrf_token": csrf_token, "access_token": auth_token},
        follow_redirects=False,
    )
    assert response.status_code == 200

    branding = get_branding(db_session)
    custom_css = branding.get("custom_css") or ""
    assert "</style>" not in custom_css.lower()
    assert "<script" not in custom_css.lower()
    assert "body{color:red;}" in custom_css


def test_branding_settings_update_requires_auth(client):
    csrf_resp = client.get("/")
    csrf_token = csrf_resp.cookies.get("csrf_token", "")

    response = client.post(
        "/settings/branding",
        data={"custom_css": "body{color:blue;}"},
        headers={"X-CSRF-Token": csrf_token},
        cookies={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers.get("location") == "/admin/login?next=/settings/branding"
