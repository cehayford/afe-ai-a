from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User
from app.modules.units.models import Unit


class PaymentPurpose(StrEnum):
    VERIFICATION_FEE = "verification_fee"
    FEATURED_LISTING = "featured_listing"
    SUBSCRIPTION = "subscription"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    WAIVED = "waived"


class Payment(Base):
    """A fee paid to Afe through the payment partner's hosted checkout. Afe never sees card
    or mobile-money details (Statement §7.2). Phase 1 collects only the verification fee;
    rent protection is Phase 2 and uses a separate, licensed flow."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    amount_pesewas: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="GHS")
    status: Mapped[str] = mapped_column(String(10), default=PaymentStatus.PENDING, index=True)
    provider: Mapped[str] = mapped_column(String(30))
    checkout_url: Mapped[str] = mapped_column(String(500), default="")
    provider_data: Mapped[dict] = mapped_column(JSON, default=dict)
    waived_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    paid_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    unit: Mapped[Unit | None] = relationship()
