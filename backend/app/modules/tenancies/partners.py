"""The licensed partner that holds tenants' money (decisions B4, B5, B7).

Afe never holds money: the partner does, and Afe only sends it instructions (charge,
release, refund) and receives signed confirmations. Which partner, and under which legal
structure, waits on counsel's written opinion (gate B7). Until then only the test partner
exists, and settings refuse to enable protected payments outside development with it.

A real partner implements the same calls. Its parse_webhook verifies the signature and sets `sent_at` from the
signed time of the delivery (not of the event), so the partner's own retries pass and a request captured and
replayed later is refused (MAX_WEBHOOK_AGE). Its release and refund must be idempotent on the reference and the
kind: repeating an instruction the partner already accepted returns the same transfer and moves no more money.
"""

import importlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.config import get_settings
from app.db import utcnow


class PartnerError(Exception):
    pass


@dataclass(frozen=True)
class Transfer:
    ref: str
    completed: bool  # False: wait for the partner's webhook


@dataclass(frozen=True)
class PartnerEvent:
    kind: str  # charge.succeeded | charge.failed | release.succeeded | release.failed | refund.succeeded | refund.failed
    reference: str  # the tenancy reference
    amount_pesewas: int
    partner_ref: str
    raw: dict = field(default_factory=dict)
    sent_at: datetime | None = None  # the signed delivery time


MAX_WEBHOOK_AGE = timedelta(minutes=5)


def is_fresh(event: PartnerEvent, now: datetime | None = None) -> bool:
    """A delivery signed within MAX_WEBHOOK_AGE of now (either way, for clock drift)."""
    sent = event.sent_at
    return sent is not None and sent.tzinfo is not None and abs((now or utcnow()) - sent) <= MAX_WEBHOOK_AGE


@dataclass(frozen=True)
class StatementLine:
    partner_ref: str
    kind: str  # charge | release | refund
    reference: str
    amount_pesewas: int


class EscrowPartner(Protocol):
    name: str

    def create_charge(self, reference: str, amount_pesewas: int, phone: str, email: str, return_url: str) -> str:
        """Start a hosted checkout that holds the money; return its URL."""

    def lookup_name(self, channel: str, account_number: str) -> str:
        """The registered name on a mobile-money wallet or bank account."""

    def release(self, reference: str, amount_pesewas: int, channel: str, account_number: str) -> Transfer: ...

    def refund(self, reference: str, amount_pesewas: int) -> Transfer: ...

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> PartnerEvent | None: ...

    def statement(self) -> list[StatementLine]:
        """The partner's record of movements, for nightly reconciliation."""


@dataclass
class _TestBook:
    lines: list[StatementLine] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)


test_book = _TestBook()

# Test wallets, like a payment provider's published test numbers: the demo landlords' own
# wallets, and one in someone else's name to try the name-match check.
DEMO_WALLETS = {
    "0244123456": "AMA OWUSU",
    "0501234567": "KOFI ASANTE",
    "0209998888": "KWAKU MENSAH",
}


class TestEscrow:
    """Development and tests only. Checkout is a page on the frontend with a Pay button;
    releases and refunds complete at once; wallet names come from `test_book.names` or
    from `DEMO_WALLETS` (add more with `register_name`)."""

    name = "test"

    def create_charge(self, reference, amount_pesewas, phone, email, return_url) -> str:
        return f"{get_settings().frontend_url}/pay/test-tenancy/{reference}"

    def lookup_name(self, channel, account_number) -> str:
        name = test_book.names.get(account_number) or DEMO_WALLETS.get(account_number)
        if name is None:
            raise PartnerError("The partner couldn't find that account.")
        return name

    def release(self, reference, amount_pesewas, channel, account_number) -> Transfer:
        ref = f"test-rel-{secrets.token_hex(5)}"
        test_book.lines.append(StatementLine(ref, "release", reference, amount_pesewas))
        return Transfer(ref, completed=True)

    def refund(self, reference, amount_pesewas) -> Transfer:
        ref = f"test-ref-{secrets.token_hex(5)}"
        test_book.lines.append(StatementLine(ref, "refund", reference, amount_pesewas))
        return Transfer(ref, completed=True)

    def parse_webhook(self, body, headers) -> PartnerEvent | None:
        data = json.loads(body)
        sent_at = datetime.fromisoformat(data["sent_at"]) if "sent_at" in data else utcnow()
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
        return PartnerEvent(data["kind"], data["reference"], int(data["amount"]), data.get("partner_ref", ""), data,
                            sent_at)

    def statement(self) -> list[StatementLine]:
        return list(test_book.lines)

    @staticmethod
    def register_name(account_number: str, name: str) -> None:
        test_book.names[account_number] = name

    @staticmethod
    def record_charge(reference: str, amount_pesewas: int) -> str:
        ref = f"test-chg-{secrets.token_hex(5)}"
        test_book.lines.append(StatementLine(ref, "charge", reference, amount_pesewas))
        return ref


def get_partner() -> EscrowPartner:
    module, _, cls = get_settings().escrow_partner.rpartition(".")
    return getattr(importlib.import_module(module), cls)()
