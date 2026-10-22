from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH]


class FlagStatus(StrEnum):
    OPEN = "open"
    DISMISSED = "dismissed"
    CONFIRMED = "confirmed"


class RiskFlag(Base):
    """A rule hit that a person must look at. Every flag says which rule fired and why."""

    __tablename__ = "risk_flags"
    __table_args__ = (Index("ix_risk_subject_status", "subject_type", "subject_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    subject_type: Mapped[str] = mapped_column(String(60))
    subject_id: Mapped[str] = mapped_column(String(40))
    rule: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(10))
    explanation: Mapped[str] = mapped_column(String(300))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=FlagStatus.OPEN)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None]
    resolution_note: Mapped[str] = mapped_column(String(300), default="")
