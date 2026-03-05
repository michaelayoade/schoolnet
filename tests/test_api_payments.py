"""Tests for payment webhook security behavior."""


def test_paystack_webhook_rejects_when_unconfigured(client, monkeypatch):
    from app.api import payments

    monkeypatch.setattr(payments.paystack_gateway, "is_configured", lambda: False)

    response = client.post(
        "/payments/webhook/paystack", content=b'{"event":"charge.success"}'
    )

    assert response.status_code == 503
    assert response.json()["message"] == "Payment webhook is not configured"


def test_paystack_webhook_rejects_invalid_signature(client, monkeypatch):
    from app.api import payments

    monkeypatch.setattr(payments.paystack_gateway, "is_configured", lambda: True)
    monkeypatch.setattr(
        payments.paystack_gateway,
        "validate_webhook_signature",
        lambda _body, _sig: False,
    )

    response = client.post(
        "/payments/webhook/paystack", content=b'{"event":"charge.success"}'
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid signature"


def test_paystack_webhook_accepts_valid_signature(client, monkeypatch):
    from app.api import payments

    called = {"ok": False}

    monkeypatch.setattr(payments.paystack_gateway, "is_configured", lambda: True)
    monkeypatch.setattr(
        payments.paystack_gateway,
        "validate_webhook_signature",
        lambda _body, _sig: True,
    )

    def _handle_webhook(self, event_type, event_id, payload):
        called["ok"] = True
        assert event_type == "charge.success"
        assert payload["event"] == "charge.success"
        assert event_id == "evt_123"

    monkeypatch.setattr(payments.ApplicationService, "handle_webhook", _handle_webhook)

    response = client.post(
        "/payments/webhook/paystack",
        content=b'{"event":"charge.success","data":{"id":"evt_123"}}',
        headers={"x-paystack-signature": "valid"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert called["ok"] is True
