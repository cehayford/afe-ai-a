"""Accounts and sign-in.

Two ways in: a code sent by SMS (everyone), or a password (staff, and anyone who sets one).
Landlords, agents and staff then pass a second step with an authenticator app. A finished
sign-in gets a short-lived access token and a rotating refresh token for that device.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import totp
from app.core.errors import DomainError, InvalidInput, NotAllowed
from app.core.ghana import normalise_phone
from app.core.security import (
    create_access_token,
    create_mfa_token,
    hash_password,
    new_refresh_token,
    read_mfa_token,
    token_digest,
    verify_password,
)
from app.db import utcnow
from app.modules.audit.log import record
from app.modules.notifications.models import DeliveryStatus
from app.modules.notifications.service import send_direct

from .models import SELF_SIGNUP_ROLES, OtpChallenge, RateEvent, RefreshToken, Role, User

# A refresh token used again within this window is treated as a race, not theft.
REUSE_GRACE = timedelta(seconds=30)


class SignInFailed(DomainError):
    status_code = 401
    code = "sign_in_failed"


class TooManyAttempts(DomainError):
    status_code = 429
    code = "too_many_attempts"


# --- Accounts --------------------------------------------------------------------------------


def create_user(
    db: Session,
    username: str,
    password: str | None,
    role: Role = Role.RENTER,
    display_name: str = "",
    phone: str | None = None,
    email: str | None = None,
) -> User:
    if password is not None and len(password) < 10:
        raise InvalidInput("Use a password of at least 10 characters.")
    user = User(
        username=username.strip().lower(),
        password_hash=hash_password(password) if password else "",
        role=Role(role),
        display_name=display_name.strip(),
        phone=normalise_phone(phone) if phone else None,
        email=email,
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError as exc:
        raise InvalidInput("That username or phone number is already registered.") from exc
    return user


def _find_by_login(db: Session, login: str) -> User | None:
    login = (login or "").strip()
    try:
        phone = normalise_phone(login)
    except InvalidInput:
        phone = None
    # Only compare phones when the login is one: `phone == None` is `phone IS NULL` in SQL, which
    # would match every account without a phone number.
    match = User.username == login.lower()
    if phone is not None:
        match = or_(match, User.phone == phone)
    return db.scalar(select(User).where(match))


def authenticate(db: Session, login: str, password: str) -> User | None:
    """Password check only. Use sign_in_with_password for the rate-limited sign-in flow."""
    user = _find_by_login(db, login)
    if user and user.is_active and user.password_hash and verify_password(password, user.password_hash):
        return user
    return None


# --- Rate limits ---------------------------------------------------------------------------------


def _hit(db: Session, key: str, limit: int, window: timedelta, message: str) -> None:
    since = utcnow() - window
    count = db.scalar(
        select(func.count()).select_from(RateEvent).where(RateEvent.key == key, RateEvent.created_at > since)
    )
    if count >= limit:
        raise TooManyAttempts(message)
    db.add(RateEvent(key=key))
    db.flush()


def rate_limit(db: Session, key: str, limit: int, window: timedelta, message: str) -> None:
    """Count one use of `key`; refuse once `limit` uses fall inside `window`."""
    _hit(db, key, limit, window, message)


# --- SMS codes ---------------------------------------------------------------------------------------


def _code_hash(phone: str, code: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def request_code(db: Session, phone: str, purpose: str, channel: str = "sms") -> None:
    """Send a 6-digit code by SMS or WhatsApp. Always looks the same to the caller, whether or not
    an account exists, so the endpoint can't be used to find out who is on Afe. If WhatsApp can't
    deliver it, the code goes by SMS instead, so nobody is left waiting for a message that won't come."""
    if purpose not in ("login", "signup"):
        raise InvalidInput("Unknown purpose.")
    phone = normalise_phone(phone)
    s = get_settings()
    _hit(
        db,
        f"otp:{phone}",
        s.otp_per_phone_per_hour,
        timedelta(hours=1),
        "Too many codes sent to this number. Try again in an hour.",
    )
    exists = db.scalar(select(User.id).where(User.phone == phone)) is not None
    if (purpose == "login" and not exists) or (purpose == "signup" and exists):
        return  # say nothing either way
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(
        OtpChallenge(
            phone=phone,
            purpose=purpose,
            code_hash=_code_hash(phone, code),
            expires_at=utcnow() + timedelta(minutes=s.otp_minutes),
        )
    )
    db.flush()
    if channel == "whatsapp":
        if send_direct(db, "whatsapp", phone, "otp", code=code).status != DeliveryStatus.FAILED:
            return
    send_direct(db, "sms", phone, "otp", code=code)


def resend_code_by_sms(db: Session, phone: str, sent_at: datetime | None = None) -> bool:
    """WhatsApp accepted a code and then couldn't deliver it (Meta's late "failed" report): send a new code by
    SMS, so nobody is left waiting. The new code replaces the one that never arrived; only its hash is kept.
    sent_at is when that message went: if the person has asked for a newer code since, it's left alone."""
    challenge = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone, OtpChallenge.consumed_at.is_(None), OtpChallenge.expires_at > utcnow())
        .order_by(OtpChallenge.created_at.desc(), OtpChallenge.id.desc())
    )
    if challenge is None or (sent_at is not None and challenge.created_at > sent_at):
        return False
    code = f"{secrets.randbelow(10**6):06d}"
    challenge.code_hash = _code_hash(phone, code)
    db.flush()
    send_direct(db, "sms", phone, "otp", code=code)
    return True


def set_whatsapp_opt_in(db: Session, user: User, on: bool, source: str) -> None:
    """Turn WhatsApp messages on or off and record when and how: settings, alert or whatsapp_stop."""
    if user.whatsapp_opt_in == on:
        return
    user.whatsapp_opt_in = on
    if on:
        user.whatsapp_opt_in_at, user.whatsapp_opt_in_source = utcnow(), source
    else:
        user.whatsapp_opt_out_at = utcnow()
    db.flush()
    record(db, user, "account.whatsapp_opt_in" if on else "account.whatsapp_opt_out", user, source=source)


def _consume_code(db: Session, phone: str, code: str, purpose: str) -> None:
    challenge = db.scalar(
        select(OtpChallenge)
        .where(
            OtpChallenge.phone == phone,
            OtpChallenge.purpose == purpose,
            OtpChallenge.consumed_at.is_(None),
            OtpChallenge.expires_at > utcnow(),
        )
        .order_by(OtpChallenge.created_at.desc(), OtpChallenge.id.desc())
    )
    wrong = SignInFailed("That code is wrong or has expired. Ask for a new one.")
    if challenge is None:
        raise wrong
    if challenge.attempts >= get_settings().otp_max_attempts:
        raise TooManyAttempts("Too many wrong codes. Ask for a new one.")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _code_hash(phone, (code or "").strip())):
        db.flush()
        raise wrong
    challenge.consumed_at = utcnow()
    db.flush()


def sign_up_with_code(
    db: Session, phone: str, code: str, display_name: str, role: str, accept_privacy: bool = False
) -> User:
    if role not in SELF_SIGNUP_ROLES:
        raise NotAllowed("You can sign up as a renter, landlord or agent.")
    if not accept_privacy:
        raise InvalidInput("Read and accept the privacy notice and terms to create an account.")
    if len(display_name.strip()) < 2:
        raise InvalidInput("Enter your name.")
    phone = normalise_phone(phone)
    _consume_code(db, phone, code, "signup")
    user = create_user(db, phone.lstrip("+"), None, Role(role), display_name, phone)
    user.phone_verified_at = utcnow()
    db.flush()
    record(db, user, "account.signed_up", user, role=role)
    from .privacy import accept_notice

    accept_notice(db, user)
    return user


def sign_in_with_code(db: Session, phone: str, code: str) -> User:
    phone = normalise_phone(phone)
    _consume_code(db, phone, code, "login")
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None or not user.is_active:
        raise SignInFailed("That code is wrong or has expired. Ask for a new one.")
    user.phone_verified_at = user.phone_verified_at or utcnow()
    return user


def sign_in_with_password(db: Session, login: str, password: str) -> User:
    _hit(
        db,
        f"login:{(login or '').strip().lower()}",
        get_settings().login_attempts_per_15_min,
        timedelta(minutes=15),
        "Too many attempts. Wait 15 minutes and try again.",
    )
    user = authenticate(db, login, password)
    if user is None:
        raise SignInFailed("Wrong username, phone number or password.")
    return user


# --- Second step and tokens ------------------------------------------------------------------------


@dataclass
class SignInResult:
    status: str  # signed_in | mfa_required | mfa_setup
    user: User
    access_token: str = ""
    refresh_token: str = ""
    expires_in: int = 0
    mfa_token: str = ""
    otpauth_uri: str = ""
    totp_secret: str = ""


def begin_session(db: Session, user: User, device: str = "", device_id: str = "") -> SignInResult:
    """After the first step: finish, or ask for the authenticator code (setting it up first
    if this person has never used one)."""
    if user.needs_mfa and get_settings().mfa_enforced:
        if user.totp_enabled_at:
            return SignInResult("mfa_required", user, mfa_token=create_mfa_token(user.id))
        if not user.totp_secret:
            user.totp_secret = totp.new_secret()
            db.flush()
        return SignInResult(
            "mfa_setup",
            user,
            mfa_token=create_mfa_token(user.id),
            totp_secret=user.totp_secret,
            otpauth_uri=totp.provisioning_uri(user.totp_secret, user.phone or user.username),
        )
    return _issue(db, user, device, device_id=device_id)


def complete_mfa(db: Session, mfa_token: str, code: str, device: str = "", device_id: str = "") -> SignInResult:
    user_id = read_mfa_token(mfa_token)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active or not user.totp_secret:
        raise SignInFailed("Your sign-in expired. Start again.")
    _hit(db, f"mfa:{user.id}", 5, timedelta(minutes=5), "Too many wrong codes. Wait 5 minutes and try again.")
    if not totp.verify(user.totp_secret, code):
        raise SignInFailed("That authenticator code is wrong. Check the time on your phone and try again.")
    if not user.totp_enabled_at:
        user.totp_enabled_at = utcnow()
        record(db, user, "account.mfa_enabled", user)
    return _issue(db, user, device, device_id=device_id)


def _issue(db: Session, user: User, device: str, family: str | None = None, device_id: str = "") -> SignInResult:
    s = get_settings()
    token = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_digest(token),
            family=family or secrets.token_hex(16),
            device=device[:200],
            device_id=device_id[:64],
            expires_at=utcnow() + timedelta(days=s.refresh_token_days),
        )
    )
    db.flush()
    if family is None:
        record(db, user, "account.signed_in", user, device=device[:120])
    return SignInResult(
        "signed_in",
        user,
        access_token=create_access_token(user.id),
        refresh_token=token,
        expires_in=s.access_token_minutes * 60,
    )


def refresh(db: Session, token: str, device: str = "") -> SignInResult:
    """Swap a refresh token for a new pair. A token used twice means it was copied: the
    whole family is revoked and the person has to sign in again."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_digest(token or "")))
    expired = SignInFailed("Your session has ended. Sign in again.")
    if row is None or row.revoked_at or row.expires_at <= utcnow():
        raise expired
    if row.used_at and utcnow() - row.used_at <= REUSE_GRACE:
        # Two requests (e.g. two tabs) refreshed with the same token at the same moment.
        user = db.get(User, row.user_id)
        if user is None or not user.is_active:
            raise expired
        return _issue(db, user, device or row.device, family=row.family, device_id=row.device_id)
    if row.used_at:
        revoke_family(db, row.family)
        record(db, None, "account.refresh_token_reused", row, user=row.user_id)
        raise expired
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise expired
    row.used_at = utcnow()
    return _issue(db, user, device or row.device, family=row.family, device_id=row.device_id)


def revoke_family(db: Session, family: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family == family, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def sign_out(db: Session, token: str) -> None:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_digest(token or "")))
    if row:
        revoke_family(db, row.family)


def sign_out_everywhere(db: Session, user: User) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    record(db, user, "account.signed_out_everywhere", user)
    return result.rowcount


def active_devices(db: Session, user: User) -> list[RefreshToken]:
    """One row per signed-in device: the newest live token in each family."""
    rows = db.scalars(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.used_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        .order_by(RefreshToken.created_at.desc())
    )
    return list(rows)
