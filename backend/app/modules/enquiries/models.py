from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User
from app.modules.listings.models import Listing


class SavedListing(Base):
    __tablename__ = "saved_listings"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="saved_listing_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    listing: Mapped[Listing] = relationship()


class Thread(Base):
    """A conversation between one renter and the lister about one listing. Contact details
    stay hidden so the conversation, and any payment talk, stays where Afe can see it."""

    __tablename__ = "threads"
    __table_args__ = (UniqueConstraint("listing_id", "renter_id", name="thread_per_renter_listing"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    renter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lister_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    renter_read_at: Mapped[datetime | None]
    lister_read_at: Mapped[datetime | None]

    listing: Mapped[Listing] = relationship()
    renter: Mapped[User] = relationship(foreign_keys=[renter_id])
    lister: Mapped[User] = relationship(foreign_keys=[lister_id])
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", order_by="Message.id")

    def other(self, user) -> User:
        return self.lister if user.id == self.renter_id else self.renter

    def unread_for(self, user) -> bool:
        seen = self.renter_read_at if user.id == self.renter_id else self.lister_read_at
        return seen is None or self.last_message_at > seen


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), comment="Null for Afe system messages")
    body: Mapped[str] = mapped_column(Text)
    warning: Mapped[str] = mapped_column(
        String(300), default="", comment="Shown to the other person, e.g. pay-first talk"
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    thread: Mapped[Thread] = relationship(back_populates="messages")
    sender: Mapped[User | None] = relationship()


class ViewingStatus(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


OPEN_VIEWING = (ViewingStatus.REQUESTED, ViewingStatus.CONFIRMED)


class Viewing(Base):
    """A renter's visit to a home. A completed viewing is required before any tenancy offer
    in Phase 2, which is what makes "never pay before you view" enforceable."""

    __tablename__ = "viewings"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"))
    renter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lister_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    requested_for: Mapped[datetime]
    note: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(12), default=ViewingStatus.REQUESTED, index=True)
    response_note: Mapped[str] = mapped_column(String(300), default="")
    responded_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    reminded_day_at: Mapped[datetime | None]
    reminded_hour_at: Mapped[datetime | None]

    listing: Mapped[Listing] = relationship()
    renter: Mapped[User] = relationship(foreign_keys=[renter_id])
    lister: Mapped[User] = relationship(foreign_keys=[lister_id])
    outcome: Mapped["ViewingOutcome | None"] = relationship(viewonly=True, uselist=False)



class ViewingOutcome(Base):
    """The renter's answer after a viewing: did they rent it, and did they pay through Afe?
    Measures leakage (build plan §13) without judging anyone."""

    __tablename__ = "viewing_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    viewing_id: Mapped[int] = mapped_column(ForeignKey("viewings.id", ondelete="CASCADE"), unique=True)
    answer: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime | None]
