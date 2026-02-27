"""Tests for payment API endpoints."""

from unittest.mock import patch


def test_paystack_webhook_returns_503_when_gateway_unconfigured(client):
    payload = {
        "event": "charge.success",
        "data": {"id": "evt_123"},
    }

    with (
        patch("app.api.payments.paystack_gateway.is_configured", return_value=False),
        patch("app.api.payments.paystack_gateway.validate_webhook_signature") as mock_validate,
        patch("app.api.payments.ApplicationService") as mock_application_service,
    ):
        response = client.post(
            "/payments/webhook/paystack",
            json=payload,
            headers={"x-paystack-signature": "fake-signature"},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "http_503"
    assert body["message"] == "Payment gateway not configured"
    mock_validate.assert_not_called()
    mock_application_service.assert_not_called()


def test_payment_callback_rejects_unverified_reference(client):
    with (
        patch(
            "app.api.payments.paystack_gateway.verify_transaction",
            return_value={"status": "failed"},
        ) as mock_verify,
        patch("app.api.payments.ApplicationService") as mock_application_service,
    ):
        response = client.get("/payments/callback?reference=ref_unverified")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "http_400"
    assert body["message"] == "Payment verification failed"
    mock_verify.assert_called_once_with("ref_unverified")
    mock_application_service.assert_not_called()
