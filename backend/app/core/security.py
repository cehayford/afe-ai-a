"""Password hashing (stdlib scrypt), short-lived JWTs, and opaque refresh tokens."""

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt

from app.config import get_settings
from app.db import utcnow

_R, _P = 8, 1


def hash_password(password: str) -> str:
    n = get_settings().password_scrypt_n
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=_R, p=_P, maxmem=2**26)
    return f"scrypt${n}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=_R, p=_P, maxmem=2**26)
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def _encode(user_id: int, kind: str, lifetime: timedelta) -> str:
    now = utcnow()
    claims = {"sub": str(user_id), "typ": kind, "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, get_settings().secret_key, algorithm="HS256")


def _decode(token: str, kind: str) -> int | None:
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return int(claims["sub"]) if claims.get("typ") == kind else None
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def create_access_token(user_id: int) -> str:
    return _encode(user_id, "access", timedelta(minutes=get_settings().access_token_minutes))


def read_access_token(token: str) -> int | None:
    return _decode(token, "access")


def create_mfa_token(user_id: int) -> str:
    """Proves the first sign-in step passed; only good for the second step, for 5 minutes."""
    return _encode(user_id, "mfa", timedelta(minutes=5))


def read_mfa_token(token: str) -> int | None:
    return _decode(token, "mfa")


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def token_digest(token: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()
