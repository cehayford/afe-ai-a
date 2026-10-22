from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User
from app.modules.areas.models import ServiceArea


class SavedSearch(Base):
    """A renter's "tell me when a home like this is listed". Empty criteria mean "any"."""

    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("service_areas.id"))
    bedrooms: Mapped[int | None] = mapped_column(comment="3 means 3 or more; 0 is a single room")
    max_rent_pesewas: Mapped[int | None]
    channel: Mapped[str] = mapped_column(String(10), default="sms", comment="sms, whatsapp or in_app")
    active: Mapped[bool] = mapped_column(default=True, index=True)
    alerts_sent: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_alert_at: Mapped[datetime | None]

    user: Mapped[User] = relationship()
    area: Mapped[ServiceArea | None] = relationship()


class AlertSent(Base):
    """One alert per search per listing, ever."""

    __tablename__ = "alerts_sent"
    __table_args__ = (UniqueConstraint("search_id", "listing_id", name="alert_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("saved_searches.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
