from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class RunStatus(StrEnum):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"
    REFUSED = "refused"
    TOO_LATE = "too_late"  # the home was decided before the run started
    CANCELLED = "cancelled"  # the agent was switched off


class AgentRun(Base):
    """One agent run: the queue entry while it waits, and the record once it ran, with its tokens and cost (Trust
    Engine: traces for every run). The packet is stored masked, as it was sent. In shadow nobody sees the answer."""

    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("agent", "visit_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(20))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("field_visits.id"))
    status: Mapped[str] = mapped_column(String(10), default=RunStatus.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(String(300), default="")
    model: Mapped[str] = mapped_column(String(40), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    packet: Mapped[dict] = mapped_column(JSON, default=dict)
    packet_sha256: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    decision: Mapped[str] = mapped_column(String(10), default="")
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    concerns: Mapped[list] = mapped_column(JSON, default=list)
    reviewer_decision: Mapped[str] = mapped_column(String(10), default="")
    reviewer_codes: Mapped[list] = mapped_column(JSON, default=list)
    agrees: Mapped[bool | None]
    false_approval: Mapped[bool | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(index=True)
    finished_at: Mapped[datetime | None]
