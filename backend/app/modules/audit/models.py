from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text, event
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, mapped_column

from app.db import Base, utcnow


class AuditEvent(Base):
    """Append-only record of every trust decision. Never updated or deleted.
    (In PostgreSQL, add a trigger or revoke UPDATE/DELETE on this table as well.)"""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_subject", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    subject_type: Mapped[str] = mapped_column(String(60))
    subject_id: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class WebhookReceipt(Base):
    """Every payment webhook as it arrived, accepted or not: evidence for a replayed or disputed confirmation.
    Written once, never changed. Kept with the payments and tenancies when an account closes."""

    __tablename__ = "webhook_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    received_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(20))  # the provider's name, e.g. paystack
    endpoint: Mapped[str] = mapped_column(String(20))  # fees or tenancies
    outcome: Mapped[str] = mapped_column(String(20))  # applied, unmatched, ignored, rejected or stale
    reference: Mapped[str] = mapped_column(String(40), default="", index=True)
    error: Mapped[str] = mapped_column(String(300), default="")
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str] = mapped_column(Text)  # all of it (to 64 KB) if the signature held; the first 2 KB if not
    size: Mapped[int] = mapped_column(default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(WebhookReceipt, "before_update")
def _no_update(*_):
    raise PermissionError("Audit events and webhook receipts are append-only")


@event.listens_for(AuditEvent, "before_delete")
@event.listens_for(WebhookReceipt, "before_delete")
def _no_delete(*_):
    raise PermissionError("Audit events and webhook receipts are append-only")


@event.listens_for(Session, "do_orm_execute")
def _no_bulk_changes(state: ORMExecuteState):
    if (state.is_update or state.is_delete) and any(m.class_ in (AuditEvent, WebhookReceipt) for m in state.all_mappers):
        raise PermissionError("Audit events are append-only")
