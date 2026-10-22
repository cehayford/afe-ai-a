from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.modules.accounts.models import User


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class IdentityCheck(Base):
    """One Ghana Card check. The card number itself is never stored: only a keyed hash
    (to find duplicate accounts) and the last four digits (to show reviewers)."""

    __tablename__ = "identity_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(10))
    card_number_hash: Mapped[str] = mapped_column(String(64), index=True)
    card_last4: Mapped[str] = mapped_column(String(4))
    name_on_card: Mapped[str] = mapped_column(String(160), default="")
    name_matches: Mapped[bool] = mapped_column(default=False)
    liveness_passed: Mapped[bool] = mapped_column(default=False)
    failure_reason: Mapped[str] = mapped_column(String(200), default="")

    user: Mapped[User] = relationship()

    @property
    def masked_card(self) -> str:
        return f"GHA-••••••{self.card_last4[:-1]}-{self.card_last4[-1]}"
