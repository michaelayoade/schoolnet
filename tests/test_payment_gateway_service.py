"""Unit tests for Paystack gateway service."""

import hashlib
import hmac
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services import payment_gateway


@pytest.fixture()
def paystack_secret_key() -> str:
    return "sk_test_abc123"


@pytest.fixture()
def configured_gateway(monkeypatch: pytest.MonkeyPatch, paystack_secret_key: str) -> payment_gateway.PaystackGateway:
    monkeypatch.setattr(payment_gateway.settings, "paystack_secret_key", paystack_secret_key)
    return payment_gateway.PaystackGateway()


@pytest.fixture()
def unconfigured_gateway(monkeypatch: pytest.MonkeyPatch) -> payment_gateway.PaystackGateway:
    monkeypatch.setattr(payment_gateway.settings, "paystack_secret_key", "")
    return payment_gateway.PaystackGateway()


@pytest.fixture()
def subaccount_request_data() -> dict[str, Any]:
    return {
        "business_name": "Acme School",
        "bank_code": "058",
        "account_number": "0001234567",
        "percentage_charge": 10.5,
    }


@pytest.fixture()
def transaction_request_data() -> dict[str, Any]:
    return {
        "amount": 500000,
        "email": "billing@example.com",
        "reference": "ref_001",
        "callback_url": "https://example.com/payments/callback",
    }


@pytest.fixture()
def webhook_payload() -> bytes:
    return b'{"event":"charge.success","data":{"id":"evt_123"}}'


@pytest.fixture()
def response_factory() -> Callable[[dict[str, Any], int], MagicMock]:
    def _build(payload: dict[str, Any], status_code: int = 200) -> MagicMock:
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload
        return response

    return _build


@pytest.fixture()
def mocked_http_client() -> tuple[MagicMock, MagicMock]:
    with patch("app.services.payment_gateway.httpx.Client") as mock_client_cls:
        mock_client = MagicMock(name="mock_httpx_client")
        mock_client_cls.return_value.__enter__.return_value = mock_client
        yield mock_client_cls, mock_client


def test_is_configured_returns_true_when_secret_key_present(configured_gateway: payment_gateway.PaystackGateway):
    assert configured_gateway.is_configured() is True


def test_is_configured_returns_false_when_secret_key_missing(unconfigured_gateway: payment_gateway.PaystackGateway):
    assert unconfigured_gateway.is_configured() is False


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    [
        (
            "create_subaccount",
            ("Acme School", "058", "0001234567", 10.5),
            {},
        ),
        (
            "update_subaccount",
            ("SUB_123",),
            {"business_name": "Updated School"},
        ),
        (
            "initialize_transaction",
            (500000, "billing@example.com", "ref_001", "https://example.com/payments/callback"),
            {},
        ),
        (
            "verify_transaction",
            ("ref_001",),
            {},
        ),
    ],
)
def test_methods_raise_runtime_error_when_gateway_unconfigured(
    method_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    unconfigured_gateway: payment_gateway.PaystackGateway,
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    mock_client_cls, _ = mocked_http_client

    method = getattr(unconfigured_gateway, method_name)
    with pytest.raises(RuntimeError, match="Paystack is not configured"):
        method(*args, **kwargs)

    mock_client_cls.assert_not_called()


def test_create_subaccount_returns_data_on_success(
    configured_gateway: payment_gateway.PaystackGateway,
    paystack_secret_key: str,
    subaccount_request_data: dict[str, Any],
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.post.return_value = response_factory(
        {
            "status": True,
            "message": "Subaccount created",
            "data": {"subaccount_code": "SUB_123", "id": 99},
        }
    )

    result = configured_gateway.create_subaccount(**subaccount_request_data)

    assert result == {"subaccount_code": "SUB_123", "id": 99}
    mock_client.post.assert_called_once_with(
        "https://api.paystack.co/subaccount",
        json=subaccount_request_data,
        headers={
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json",
        },
    )


def test_create_subaccount_raises_value_error_on_api_failure(
    configured_gateway: payment_gateway.PaystackGateway,
    subaccount_request_data: dict[str, Any],
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.post.return_value = response_factory(
        {
            "status": False,
            "message": "Invalid account details",
            "data": None,
        },
        status_code=400,
    )

    with pytest.raises(ValueError, match="Invalid account details"):
        configured_gateway.create_subaccount(**subaccount_request_data)


def test_update_subaccount_returns_data_on_success(
    configured_gateway: payment_gateway.PaystackGateway,
    paystack_secret_key: str,
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    update_data = {"business_name": "Updated School", "percentage_charge": 12.0}
    mock_client.put.return_value = response_factory(
        {
            "status": True,
            "message": "Subaccount updated",
            "data": {"subaccount_code": "SUB_123", "business_name": "Updated School"},
        }
    )

    result = configured_gateway.update_subaccount("SUB_123", **update_data)

    assert result == {"subaccount_code": "SUB_123", "business_name": "Updated School"}
    mock_client.put.assert_called_once_with(
        "https://api.paystack.co/subaccount/SUB_123",
        json=update_data,
        headers={
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json",
        },
    )


def test_update_subaccount_raises_value_error_on_api_failure(
    configured_gateway: payment_gateway.PaystackGateway,
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.put.return_value = response_factory(
        {
            "status": False,
            "message": "Subaccount not found",
            "data": None,
        },
        status_code=404,
    )

    with pytest.raises(ValueError, match="Subaccount not found"):
        configured_gateway.update_subaccount("SUB_UNKNOWN", business_name="Any Name")


def test_initialize_transaction_returns_data_on_success_with_split(
    configured_gateway: payment_gateway.PaystackGateway,
    paystack_secret_key: str,
    transaction_request_data: dict[str, Any],
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.post.return_value = response_factory(
        {
            "status": True,
            "message": "Authorization URL created",
            "data": {"authorization_url": "https://checkout.paystack.com/tx123"},
        }
    )

    result = configured_gateway.initialize_transaction(
        **transaction_request_data,
        subaccount_code="SUB_123",
        bearer="subaccount",
    )

    assert result == {"authorization_url": "https://checkout.paystack.com/tx123"}
    mock_client.post.assert_called_once_with(
        "https://api.paystack.co/transaction/initialize",
        json={
            **transaction_request_data,
            "subaccount": "SUB_123",
            "bearer": "subaccount",
        },
        headers={
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json",
        },
    )


def test_initialize_transaction_raises_value_error_on_api_failure(
    configured_gateway: payment_gateway.PaystackGateway,
    transaction_request_data: dict[str, Any],
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.post.return_value = response_factory(
        {
            "status": False,
            "message": "Amount must be at least 100",
            "data": None,
        },
        status_code=422,
    )

    with pytest.raises(ValueError, match="Amount must be at least 100"):
        configured_gateway.initialize_transaction(**transaction_request_data)


def test_verify_transaction_returns_data_on_success(
    configured_gateway: payment_gateway.PaystackGateway,
    paystack_secret_key: str,
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.get.return_value = response_factory(
        {
            "status": True,
            "message": "Verification successful",
            "data": {"reference": "ref_001", "status": "success"},
        }
    )

    result = configured_gateway.verify_transaction("ref_001")

    assert result == {"reference": "ref_001", "status": "success"}
    mock_client.get.assert_called_once_with(
        "https://api.paystack.co/transaction/verify/ref_001",
        headers={
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json",
        },
    )


def test_verify_transaction_raises_value_error_on_api_failure(
    configured_gateway: payment_gateway.PaystackGateway,
    response_factory: Callable[[dict[str, Any], int], MagicMock],
    mocked_http_client: tuple[MagicMock, MagicMock],
):
    _, mock_client = mocked_http_client
    mock_client.get.return_value = response_factory(
        {
            "status": False,
            "message": "Transaction not found",
            "data": None,
        },
        status_code=404,
    )

    with pytest.raises(ValueError, match="Transaction not found"):
        configured_gateway.verify_transaction("ref_missing")


def test_validate_webhook_signature_returns_true_for_valid_signature(
    configured_gateway: payment_gateway.PaystackGateway,
    paystack_secret_key: str,
    webhook_payload: bytes,
):
    signature = hmac.new(
        paystack_secret_key.encode("utf-8"),
        webhook_payload,
        hashlib.sha512,
    ).hexdigest()

    assert configured_gateway.validate_webhook_signature(webhook_payload, signature) is True


def test_validate_webhook_signature_returns_false_for_invalid_signature(
    configured_gateway: payment_gateway.PaystackGateway,
    webhook_payload: bytes,
):
    assert configured_gateway.validate_webhook_signature(webhook_payload, "invalid-signature") is False
