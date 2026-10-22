"""Time-based one-time passwords (RFC 6238), compatible with Google Authenticator,
Microsoft Authenticator and similar apps. Standard library only."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def now_code(secret: str, at: float | None = None) -> str:
    return _code(secret, int((at if at is not None else time.time()) // STEP))


def verify(secret: str, code: str, at: float | None = None, window: int = 1) -> bool:
    """Accept the current code and one step either side, for phone clock drift."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == DIGITS):
        return False
    counter = int((at if at is not None else time.time()) // STEP)
    return any(hmac.compare_digest(_code(secret, counter + d), code) for d in range(-window, window + 1))


def provisioning_uri(secret: str, account: str, issuer: str = "Afe") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
