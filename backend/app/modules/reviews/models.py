from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User


class Review(Base):
    """A tenant's review of a landlord and home. Only possible from a tenancy whose money
    was released, so every review comes from someone who really rented (brief §3)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenancy_id: Mapped[int] = mapped_column(ForeignKey("tenancies.id"), unique=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    landlord_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    rating: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(default=False, comment="Hidden by a reviewer (abuse, personal data)")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    author: Mapped[User] = relationship(foreign_keys=[author_id])
