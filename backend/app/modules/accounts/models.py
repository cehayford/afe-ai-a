from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class Role(StrEnum):
    RENTER = "renter"
    LANDLORD = "landlord"
    AGENT = "agent"
    FIELD_VERIFIER = "field_verifier"
    REVIEWER = "reviewer"
    ADMIN = "admin"


ROLE_LABELS = {
    Role.RENTER: "Renter",
    Role.LANDLORD: "Landlord",
    Role.AGENT: "Agent",
    Role.FIELD_VERIFIER: "Field verifier",
    Role.REVIEWER: "Trust & safety reviewer",
    Role.ADMIN: "Afe admin",
}
LISTER_ROLES = {Role.LANDLORD, Role.AGENT}
REVIEWER_ROLES = {Role.REVIEWER, Role.ADMIN}
STAFF_ROLES = {Role.FIELD_VERIFIER, Role.REVIEWER, Role.ADMIN}
# Roles that must use a second factor (TOTP) to sign in (Statement §5.1).
MFA_ROLES = LISTER_ROLES | STAFF_ROLES
SELF_SIGNUP_ROLES = {Role.RENTER, Role.LANDLORD, Role.AGENT}


class User(Base):
    """One person is one account, whatever roles they play (the plan's "party")."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str | None] = mapped_column(String(16), unique=True, comment="E.164, e.g. +233244123456")
    phone_verified_at: Mapped[datetime | None]
    email: Mapped[str | None] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20), default=Role.RENTER)
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    # TODO(staging): encrypt with a KMS data key before storing real secrets.
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled_at: Mapped[datetime | None]
    whatsapp_opt_in: Mapped[bool] = mapped_column(default=False)
    # When and how the person turned WhatsApp messages on (settings or an alert) or off. Meta requires an
    # opt-in, and this is the evidence if the number's quality rating drops.
    whatsapp_opt_in_at: Mapped[datetime | None]
    whatsapp_opt_in_source: Mapped[str] = mapped_column(String(20), default="", server_default="")
    whatsapp_opt_out_at: Mapped[datetime | None]
    # Which privacy notice and terms the person accepted, and when (Act 843 consent record).
    privacy_version: Mapped[str] = mapped_column(String(20), default="", server_default="")
    privacy_accepted_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def name(self) -> str:
        return self.display_name or self.username

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[Role(self.role)]

    @property
    def is_lister(self) -> bool:
        return self.role in LISTER_ROLES

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def can_review(self) -> bool:
        return self.role in REVIEWER_ROLES

    @property
    def needs_mfa(self) -> bool:
        return self.role in MFA_ROLES

    def __repr__(self) -> str:
        return f"<User {self.id} {self.username} {self.role}>"


class OtpChallenge(Base):
    """A one-time code sent by SMS for signing up or signing in. Only a keyed hash is kept."""

    __tablename__ = "otp_challenges"
    __table_args__ = (Index("ix_otp_phone_created", "phone", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str] = mapped_column(String(10))  # login | signup
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class RefreshToken(Base):
    """A long-lived sign-in on one device. Rotated on every use; reusing an old token
    revokes the whole family, which catches a stolen token."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family: Mapped[str] = mapped_column(String(32), index=True)
    device: Mapped[str] = mapped_column(String(200), default="")
    # Random ID from the web app's first-party cookie; links accounts used on one device (Phase 3).
    device_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class RateEvent(Base):
    """One attempt at something rate-limited (sign-in, code requests). Old rows can be
    pruned daily; in production this moves to Redis."""

    __tablename__ = "rate_events"
    __table_args__ = (Index("ix_rate_key_created", "key", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
