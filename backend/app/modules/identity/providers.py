"""KYC providers sit behind one interface, so a new provider or country is a new class
(plan §17), not a change to the verification logic."""

import importlib
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings


@dataclass(frozen=True)
class KycResult:
    passed: bool
    reference: str
    name_on_card: str = ""
    name_matches: bool = False
    liveness_passed: bool = False
    failure_reason: str = ""
    raw: dict = field(default_factory=dict)


class KycProvider(Protocol):
    name: str

    def verify_ghana_card(self, card_number: str, full_name: str, selfie: bytes | None) -> KycResult: ...


class FakeKycProvider:
    """Development and test stand-in. Card numbers ending in -0 fail; everything else passes
    with the name given. Settings refuse to load it in production."""

    name = "fake"

    def verify_ghana_card(self, card_number: str, full_name: str, selfie: bytes | None) -> KycResult:
        reference = f"fake-{card_number[-5:]}"
        if card_number.endswith("-0"):
            return KycResult(passed=False, reference=reference, failure_reason="Card not found at NIA")
        return KycResult(
            passed=True,
            reference=reference,
            name_on_card=full_name,
            name_matches=True,
            liveness_passed=selfie is not None,
        )


def get_provider() -> KycProvider:
    module_path, _, class_name = get_settings().kyc_provider.rpartition(".")
    return getattr(importlib.import_module(module_path), class_name)()
