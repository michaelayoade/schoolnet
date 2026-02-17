"""Paystack payment gateway integration."""

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PAYSTACK_BASE_URL = "https://api.paystack.co"


class PaystackGateway:
    """Thin wrapper around Paystack REST API."""

    def __init__(self) -> None:
        self._secret_key = settings.paystack_secret_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
        }

    def is_configured(self) -> bool:
        return bool(self._secret_key)

    # ── Subaccount management ────────────────────────────

    def create_subaccount(
        self,
        business_name: str,
        bank_code: str,
        account_number: str,
        percentage_charge: float,
    ) -> dict[str, Any]:
        """Create a Paystack subaccount for split payments."""
        if not self.is_configured():
            raise RuntimeError("Paystack is not configured")
        payload = {
            "business_name": business_name,
            "bank_code": bank_code,
            "account_number": account_number,
            "percentage_charge": percentage_charge,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{PAYSTACK_BASE_URL}/subaccount",
                json=payload,
                headers=self._headers(),
            )
        data = resp.json()
        if not data.get("status"):
            logger.error("Paystack create_subaccount failed: %s", data.get("message"))
            raise ValueError(data.get("message", "Failed to create subaccount"))
        logger.info("Created Paystack subaccount: %s", data["data"]["subaccount_code"])
        result: dict[str, Any] = data["data"]
        return result

    def update_subaccount(
        self,
        subaccount_code: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a Paystack subaccount."""
        if not self.is_configured():
            raise RuntimeError("Paystack is not configured")
        with httpx.Client(timeout=30) as client:
            resp = client.put(
                f"{PAYSTACK_BASE_URL}/subaccount/{subaccount_code}",
                json=kwargs,
                headers=self._headers(),
            )
        data = resp.json()
        if not data.get("status"):
            logger.error("Paystack update_subaccount failed: %s", data.get("message"))
            raise ValueError(data.get("message", "Failed to update subaccount"))
        result: dict[str, Any] = data["data"]
        return result

    def list_banks(self, country: str = "nigeria") -> list[dict[str, Any]]:
        """Get list of Nigerian banks."""
        if not self.is_configured():
            raise RuntimeError("Paystack is not configured")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{PAYSTACK_BASE_URL}/bank",
                params={"country": country},
                headers=self._headers(),
            )
        data = resp.json()
        if not data.get("status"):
            return []
        result: list[dict[str, Any]] = data["data"]
        return result

    # ── Transaction with split ───────────────────────────

    def initialize_transaction(
        self,
        amount: int,
        email: str,
        reference: str,
        callback_url: str,
        subaccount_code: str | None = None,
        bearer: str = "account",
    ) -> dict[str, Any]:
        """Initialize a Paystack transaction with optional split."""
        if not self.is_configured():
            raise RuntimeError("Paystack is not configured")
        payload: dict[str, Any] = {
            "amount": amount,
            "email": email,
            "reference": reference,
            "callback_url": callback_url,
        }
        if subaccount_code:
            payload["subaccount"] = subaccount_code
            payload["bearer"] = bearer
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{PAYSTACK_BASE_URL}/transaction/initialize",
                json=payload,
                headers=self._headers(),
            )
        data = resp.json()
        if not data.get("status"):
            logger.error("Paystack initialize failed: %s", data.get("message"))
            raise ValueError(data.get("message", "Failed to initialize transaction"))
        logger.info("Initialized Paystack transaction: %s", reference)
        result: dict[str, Any] = data["data"]
        return result

    def verify_transaction(self, reference: str) -> dict[str, Any]:
        """Verify a Paystack transaction by reference."""
        if not self.is_configured():
            raise RuntimeError("Paystack is not configured")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
                headers=self._headers(),
            )
        data = resp.json()
        if not data.get("status"):
            logger.error("Paystack verify failed: %s", data.get("message"))
            raise ValueError(data.get("message", "Failed to verify transaction"))
        result: dict[str, Any] = data["data"]
        return result

    # ── Webhook ──────────────────────────────────────────

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate Paystack webhook HMAC signature."""
        expected = hmac.new(
            self._secret_key.encode("utf-8"),
            payload,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


paystack_gateway = PaystackGateway()
