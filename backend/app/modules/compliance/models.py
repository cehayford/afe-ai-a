from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


class RuleStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


_ACTIVE = text("status = 'active'")


class ComplianceRule(Base):
    """One version of one rule (Statement §7.1: "the law is configuration"). A change is
    proposed by one reviewer and approved by a different one; approving supersedes the
    previous active version. Rows are never edited after approval."""

    __tablename__ = "compliance_rules"
    __table_args__ = (
        Index("uq_compliance_one_active_per_key", "country", "key", unique=True,
              sqlite_where=_ACTIVE, postgresql_where=_ACTIVE),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    country: Mapped[str] = mapped_column(String(2), default="GH")
    key: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[dict] = mapped_column(JSON, comment='{"v": <value>} so any JSON type fits')
    version: Mapped[int]
    source: Mapped[str] = mapped_column(String(300), comment="Law, decision or policy this comes from")
    status: Mapped[str] = mapped_column(String(10), default=RuleStatus.PROPOSED)
    proposed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    proposed_at: Mapped[datetime] = mapped_column(default=utcnow)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None]

    proposed_by = relationship("User", foreign_keys=[proposed_by_id])
