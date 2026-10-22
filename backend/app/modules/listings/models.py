import secrets
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.core.ghana import format_ghs
from app.db import Base, TimestampMixin
from app.modules.accounts.models import User
from app.modules.units.models import Unit


class ListingStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    LIVE = "live"
    PAUSED = "paused"
    LET = "let"
    ARCHIVED = "archived"


ACTIVE_STATUSES = (ListingStatus.PENDING_REVIEW, ListingStatus.LIVE, ListingStatus.PAUSED)
_ACTIVE_SQL = text("status IN ('pending_review', 'live', 'paused')")


def new_reference() -> str:
    # Short, unambiguous, easy to read out over the phone: AFE-7K3M9Q
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    return "AFE-" + "".join(secrets.choice(alphabet) for _ in range(6))


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (
        # One home, one record: a unit can have only one active listing at a time.
        Index(
            "uq_listings_one_active_per_unit",
            "unit_id",
            unique=True,
            sqlite_where=_ACTIVE_SQL,
            postgresql_where=_ACTIVE_SQL,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(10), unique=True, default=new_reference)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    lister_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(90))
    description: Mapped[str] = mapped_column(Text)
    rent_pesewas: Mapped[int] = mapped_column(comment="Monthly rent in pesewas (GH₵1 = 100)")
    advance_months: Mapped[int]
    min_lease_months: Mapped[int] = mapped_column(default=12)
    available_from: Mapped[date]
    status: Mapped[str] = mapped_column(String(16), default=ListingStatus.DRAFT, index=True)
    published_at: Mapped[datetime | None]
    status_reason: Mapped[str] = mapped_column(String(200), default="")

    unit: Mapped[Unit] = relationship()
    lister: Mapped[User] = relationship()

    @property
    def rent_display(self) -> str:
        return format_ghs(self.rent_pesewas)

    @property
    def advance_total_pesewas(self) -> int:
        return self.rent_pesewas * self.advance_months


class FeaturedPlacement(Base):
    """Paid visibility: a verified, live listing shown first in search for a period
    (Statement §12.1; build plan Phase 2). Paid through the same hosted checkout as fees."""

    __tablename__ = "featured_placements"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), unique=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime] = mapped_column(index=True)
