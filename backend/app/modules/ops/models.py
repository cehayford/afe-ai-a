from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User


class AppealStatus(StrEnum):
    OPEN = "open"
    UPHELD = "upheld"
    REJECTED = "rejected"


class AppealKind(StrEnum):
    VERIFICATION = "verification"  # a rejected identity or home verification
    LISTING = "listing"  # a listing paused or taken down
    REPORT = "report"  # an upheld scam report against this person


class Appeal(Base):
    """One appeal per decision (decision B12), decided by a reviewer who didn't make it."""

    __tablename__ = "appeals"
    __table_args__ = (UniqueConstraint("kind", "subject_id", name="one_appeal_per_decision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(15))
    subject_id: Mapped[int] = mapped_column(comment="Verification, listing or fraud report id")
    appellant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_decider_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=AppealStatus.OPEN, index=True)
    outcome: Mapped[str] = mapped_column(String(500), default="")
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None]

    appellant: Mapped[User] = relationship(foreign_keys=[appellant_id])


class LabelCheck(Base):
    """A second reviewer re-decides a sample of labels, so models train only on labels people
    agree on (roadmap workstream C)."""

    __tablename__ = "label_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("detection_labels.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True, comment="pending, agreed, disagreed")
    checked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    checked_at: Mapped[datetime | None]


class ExternalPhoto(Base):
    """A photo hash from a public listing site, imported from a crawl those sites' terms allow.
    Afe never stores the image itself, only its hashes and where it was seen."""

    __tablename__ = "external_photos"
    __table_args__ = (Index("ix_external_photos_phash", "phash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(60), comment="Site name")
    url: Mapped[str] = mapped_column(String(500))
    phash: Mapped[str] = mapped_column(String(16))
    dhash: Mapped[str] = mapped_column(String(16), default="")
    seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    matched_unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
