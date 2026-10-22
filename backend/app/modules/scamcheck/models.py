from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    API = "api"


class Lookup(Base):
    """One "Check before you pay" search. Counts feed the plan's weekly metrics."""

    __tablename__ = "scamcheck_lookups"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    channel: Mapped[str] = mapped_column(String(10), default=Channel.WEB)
    query_kind: Mapped[str] = mapped_column(String(10))  # phone | reference | invalid
    query: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(20))


class ReportStatus(StrEnum):
    NEW = "new"
    UPHELD = "upheld"
    NOT_UPHELD = "not_upheld"


class FraudReport(Base):
    """A renter's report of a suspected scam. Phase 3's main source of fraud examples."""

    __tablename__ = "fraud_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    channel: Mapped[str] = mapped_column(String(10), default=Channel.WEB)
    reported_phone: Mapped[str] = mapped_column(String(16), default="")
    reported_reference: Mapped[str] = mapped_column(String(10), default="")
    what_happened: Mapped[str] = mapped_column(Text)
    amount_lost_pesewas: Mapped[int | None]
    reporter_contact: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(12), default=ReportStatus.NEW)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str] = mapped_column(String(300), default="")
