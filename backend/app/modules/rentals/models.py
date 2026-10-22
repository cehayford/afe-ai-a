"""Landlord and agent tools (roadmap workstream G): the homes a landlord lets, whether or
not the tenant came through Afe."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User
from app.modules.units.models import Unit


class Plan(StrEnum):
    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(10), default=Plan.FREE)
    period_end: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime | None]


class RentalStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class Rental(Base):
    """A tenant in one of the landlord's homes, with the rent schedule."""

    __tablename__ = "rentals"

    id: Mapped[int] = mapped_column(primary_key=True)
    landlord_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    tenancy_id: Mapped[int | None] = mapped_column(ForeignKey("tenancies.id"), unique=True,
                                                  comment="Set when the tenant came through Afe")
    tenant_name: Mapped[str] = mapped_column(String(120))
    tenant_phone: Mapped[str] = mapped_column(String(16), default="")
    tenant_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True,
                                                      comment="The tenant's own Afe account, if they have one")
    rent_pesewas: Mapped[int]
    pay_every_months: Mapped[int] = mapped_column(default=1, comment="1 = monthly; 6 or 12 = paid in advance")
    start_date: Mapped[date]
    end_date: Mapped[date]
    next_due_date: Mapped[date]
    reminded_for: Mapped[date | None] = mapped_column(comment="The due date the last reminder was for")
    status: Mapped[str] = mapped_column(String(10), default=RentalStatus.ACTIVE, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    landlord: Mapped[User] = relationship(foreign_keys=[landlord_id])
    tenant_user: Mapped[User | None] = relationship(foreign_keys=[tenant_user_id])
    unit: Mapped[Unit | None] = relationship()


class RentPayment(Base):
    """Rent the landlord received, recorded by the landlord (or by Afe for protected payments)."""

    __tablename__ = "rent_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id", ondelete="CASCADE"), index=True)
    receipt_no: Mapped[str] = mapped_column(String(20), unique=True)
    amount_pesewas: Mapped[int]
    paid_on: Mapped[date]
    method: Mapped[str] = mapped_column(String(10), comment="momo, bank, cash or afe")
    covers_months: Mapped[int]
    note: Mapped[str] = mapped_column(String(300), default="")
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Maintenance(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id", ondelete="CASCADE"), index=True)
    raised_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120))
    details: Mapped[str] = mapped_column(Text)
    photo_key: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="open", index=True, comment="open, in_progress, done")
    landlord_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime | None]


class Agreement(Base):
    """A tenancy agreement from the rental's terms, signed in the app by both sides."""

    __tablename__ = "rental_agreements"

    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64), comment="SHA-256 of the text both people signed")
    landlord_signed_name: Mapped[str] = mapped_column(String(120), default="")
    landlord_signed_at: Mapped[datetime | None]
    tenant_signed_name: Mapped[str] = mapped_column(String(120), default="")
    tenant_signed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Renewal(Base):
    __tablename__ = "rental_renewals"

    id: Mapped[int] = mapped_column(primary_key=True)
    rental_id: Mapped[int] = mapped_column(ForeignKey("rentals.id", ondelete="CASCADE"), index=True)
    new_end_date: Mapped[date]
    new_rent_pesewas: Mapped[int]
    advance_months: Mapped[int]
    status: Mapped[str] = mapped_column(String(10), default="offered", comment="offered, accepted, declined")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None]
