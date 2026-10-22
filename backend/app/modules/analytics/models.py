from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

# Only these names are accepted, so the table stays useful for the plan's metrics (§13).
EVENT_NAMES = {
    "page_view",
    "search",
    "listing_view",
    "listing_save",
    "enquiry_start",
    "viewing_request",
    "check_lookup",
    "signup_start",
    "signup_complete",
    "fee_checkout_start",
}


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    anonymous_id: Mapped[str] = mapped_column(String(64), default="")
    path: Mapped[str] = mapped_column(String(300), default="")
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
