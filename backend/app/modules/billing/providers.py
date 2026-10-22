"""Payment partners behind one interface (decision B4 picks the partner).

A provider creates a hosted checkout and verifies the partner's signed webhook. Afe only
trusts the webhook, never the browser's return to the site, to mark a payment as paid.
"""

import hashlib
import hmac
import importlib
import json
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings


class PaymentError(Exception):
    pass


@dataclass(frozen=True)
class Checkout:
    url: str
    provider_data: dict


@dataclass(frozen=True)
class WebhookEvent:
    reference: str
    paid: bool
    amount_pesewas: int
    currency: str
    raw: dict


class PaymentProvider(Protocol):
    name: str

    def create_checkout(
        self, reference: str, amount_pesewas: int, email: str, phone: str, return_url: str
    ) -> Checkout: ...

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent | None:
        """Verify the signature and return the event, or None if it is not a payment result."""


class FakePayments:
    """Development and tests: checkout is a page on the frontend with a "Pay" button that
    calls POST /api/v1/payments/test/{reference}/complete (only available in debug)."""

    name = "fake"

    def create_checkout(self, reference, amount_pesewas, email, phone, return_url) -> Checkout:
        return Checkout(url=f"{get_settings().frontend_url}/pay/test/{reference}", provider_data={})

    def parse_webhook(self, body, headers):
        data = json.loads(body)
        return WebhookEvent(data["reference"], data.get("paid", True), data["amount"], "GHS", data)


class Paystack:
    """Paystack hosted checkout with mobile money (MTN, Telecel, AT) and cards."""

    name = "paystack"
    API = "https://api.paystack.co"

    def _secret(self) -> str:
        key = get_settings().paystack_secret_key
        if not key:
            raise PaymentError("AFE_PAYSTACK_SECRET_KEY is not set")
        return key

    def create_checkout(self, reference, amount_pesewas, email, phone, return_url) -> Checkout:
        payload = {
            "reference": reference,
            "amount": amount_pesewas,
            "currency": "GHS",
            # Paystack requires an email; people without one get a non-deliverable placeholder.
            "email": email or f"{phone.lstrip('+')}@customers.afe.invalid",
            "callback_url": return_url,
            "channels": ["mobile_money", "card"],
            "metadata": {"phone": phone},
        }
        req = urllib.request.Request(  # noqa: S310 - fixed https URL
            f"{self.API}/transaction/initialize",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self._secret()}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310
                data = json.load(res)
        except OSError as exc:
            raise PaymentError(f"Paystack is unreachable: {exc}") from exc
        if not data.get("status"):
            raise PaymentError(data.get("message", "Paystack refused the checkout"))
        return Checkout(
            url=data["data"]["authorization_url"], provider_data={"access_code": data["data"]["access_code"]}
        )

    def parse_webhook(self, body, headers):
        signature = headers.get("x-paystack-signature", "")
        expected = hmac.new(self._secret().encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise PaymentError("Bad webhook signature")
        event = json.loads(body)
        if event.get("event") != "charge.success":
            return None
        data = event["data"]
        return WebhookEvent(
            data["reference"], data.get("status") == "success", int(data["amount"]), data["currency"], event
        )


def get_provider() -> PaymentProvider:
    module, _, cls = get_settings().payment_provider.rpartition(".")
    return getattr(importlib.import_module(module), cls)()
