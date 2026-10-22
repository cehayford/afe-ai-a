"""Ghana-specific formats: digital addresses, Ghana Card numbers, phone numbers, money."""

import hashlib
import hmac
import re

from app.config import get_settings
from app.core.errors import InvalidInput

_DIGITAL_ADDRESS = re.compile(r"^([A-Z]{2})-?(\d{3,4})-?(\d{4})$")
_GHANA_CARD = re.compile(r"^GHA-?(\d{9})-?(\d)$")
_LOCAL_PHONE = re.compile(r"^0(\d{9})$")
_INTL_PHONE = re.compile(r"^(?:\+|00)?233(\d{9})$")


def normalise_digital_address(value: str) -> str:
    """GhanaPost GPS address, e.g. 'ga1838164' -> 'GA-183-8164'."""
    cleaned = re.sub(r"\s+", "", value or "").upper()
    match = _DIGITAL_ADDRESS.match(cleaned)
    if not match:
        raise InvalidInput("Enter a GhanaPost digital address like GA-183-8164.")
    return "-".join(match.groups())


def normalise_ghana_card(value: str) -> str:
    """Ghana Card PIN, e.g. 'gha 123456789 0' -> 'GHA-123456789-0'."""
    cleaned = re.sub(r"\s+", "", value or "").upper()
    match = _GHANA_CARD.match(cleaned)
    if not match:
        raise InvalidInput("Enter a Ghana Card number like GHA-123456789-0.")
    return f"GHA-{match.group(1)}-{match.group(2)}"


def normalise_phone(value: str) -> str:
    """Ghana mobile number in E.164, e.g. '024 412 3456' -> '+233244123456'."""
    cleaned = re.sub(r"[\s\-()]", "", value or "")
    for pattern in (_LOCAL_PHONE, _INTL_PHONE):
        match = pattern.match(cleaned)
        if match:
            return f"+233{match.group(1)}"
    raise InvalidInput("Enter a Ghana phone number like 024 412 3456.")


def pii_hash(value: str) -> str:
    """Keyed hash for matching identity numbers without storing them."""
    key = get_settings().pii_hash_key.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def format_ghs(pesewas: int) -> str:
    """Money is stored in pesewas (GH₵1 = 100 pesewas)."""
    cedis, rem = divmod(int(pesewas), 100)
    return f"GH₵{cedis:,}" if rem == 0 else f"GH₵{cedis:,}.{rem:02d}"
