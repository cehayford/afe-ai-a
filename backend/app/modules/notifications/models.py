from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"  # WhatsApp only: Meta's delivery report
    READ = "read"  # WhatsApp only
    FAILED = "failed"


class Notification(Base):
    """One message to one person on one channel. Doubles as the outbox and the in-app inbox.
    Sensitive bodies (sign-in codes) are stored redacted."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    recipient: Mapped[str] = mapped_column(String(254), default="")
    template: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(300), default="", comment="Frontend path to open, e.g. /account/viewings")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=DeliveryStatus.QUEUED)
    provider: Mapped[str] = mapped_column(String(40), default="")
    provider_ref: Mapped[str] = mapped_column(String(120), default="", index=True)  # Meta's delivery reports
    error: Mapped[str] = mapped_column(String(300), default="")
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    # For an SMS sent because WhatsApp couldn't deliver: the WhatsApp message it stands in for.
    fallback_of_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    sent_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    read_at: Mapped[datetime | None]
