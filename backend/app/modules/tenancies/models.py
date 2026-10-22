from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Index, String, Text, event, text
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, mapped_column, relationship

from app.db import Base, TimestampMixin, utcnow
from app.modules.accounts.models import User
from app.modules.listings.models import Listing
from app.modules.units.models import Unit


class TenancyStatus(StrEnum):
    OFFERED = "offered"  # landlord offered terms after a completed viewing
    FUNDING = "funding"  # tenant accepted and is paying at the partner's checkout
    FUNDED = "funded"  # money held by the partner; home locked; waiting for move-in
    DISPUTED = "disputed"  # either side raised a problem; a reviewer decides
    RELEASE_PENDING = "release_pending"  # pilot: waiting for a reviewer to approve the release
    RELEASING = "releasing"  # payout sent to the partner, waiting for confirmation
    RELEASED = "released"  # landlord paid (end)
    REFUNDING = "refunding"
    REFUNDED = "refunded"  # tenant paid back (end)
    DECLINED = "declined"  # tenant said no (end)
    WITHDRAWN = "withdrawn"  # landlord took the offer back (end)
    EXPIRED = "expired"  # offer or checkout lapsed (end)


HOLDING = (
    TenancyStatus.FUNDED, TenancyStatus.DISPUTED, TenancyStatus.RELEASE_PENDING,
    TenancyStatus.RELEASING, TenancyStatus.REFUNDING,
)
ACTIVE = (TenancyStatus.OFFERED, TenancyStatus.FUNDING, *HOLDING)
_ACTIVE_SQL = text(
    "status IN ('offered', 'funding', 'funded', 'disputed', 'release_pending', 'releasing', 'refunding')"
)


class Tenancy(TimestampMixin, Base):
    """A let agreed through Afe, and the protected payment that goes with it."""

    __tablename__ = "tenancies"
    __table_args__ = (
        # One home, one tenancy in progress at a time: the double-letting scam is impossible.
        Index("uq_tenancies_one_active_per_unit", "unit_id", unique=True,
              sqlite_where=_ACTIVE_SQL, postgresql_where=_ACTIVE_SQL),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    landlord_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    viewing_id: Mapped[int] = mapped_column(ForeignKey("viewings.id"))
    payee_id: Mapped[int] = mapped_column(ForeignKey("payees.id"))

    rent_pesewas: Mapped[int]
    advance_months: Mapped[int]
    deposit_months: Mapped[int]
    lease_months: Mapped[int]
    move_in_date: Mapped[date]
    held_pesewas: Mapped[int] = mapped_column(comment="Advance rent + deposit, held by the partner")
    fee_pesewas: Mapped[int] = mapped_column(comment="Afe protection fee")
    fee_payer: Mapped[str] = mapped_column(String(10))
    charge_pesewas: Mapped[int] = mapped_column(comment="What the tenant pays at checkout")
    payout_pesewas: Mapped[int] = mapped_column(comment="What the landlord receives on release")
    rule_versions: Mapped[dict] = mapped_column(JSON, default=dict, comment="Compliance rule versions applied")

    status: Mapped[str] = mapped_column(String(16), default=TenancyStatus.OFFERED, index=True)
    offer_expires_at: Mapped[datetime]
    agreement_key: Mapped[str] = mapped_column(String(200), default="", comment="Signed agreement in private storage")
    move_in_photo_key: Mapped[str] = mapped_column(String(200), default="", server_default="",
                                                   comment="Tenant's move-in photo, private: evidence for disputes")
    checkout_url: Mapped[str] = mapped_column(String(500), default="")
    accepted_at: Mapped[datetime | None]
    funded_at: Mapped[datetime | None]
    tenant_confirmed_at: Mapped[datetime | None]
    landlord_evidence_at: Mapped[datetime | None]
    landlord_evidence: Mapped[str] = mapped_column(Text, default="")
    closed_at: Mapped[datetime | None]
    close_reason: Mapped[str] = mapped_column(String(300), default="")

    listing: Mapped[Listing] = relationship()
    unit: Mapped[Unit] = relationship()
    landlord: Mapped[User] = relationship(foreign_keys=[landlord_id])
    tenant: Mapped[User] = relationship(foreign_keys=[tenant_id])
    payee: Mapped["Payee"] = relationship()


class LedgerKind(StrEnum):
    CHARGE_STARTED = "charge_started"
    CHARGE_SUCCEEDED = "charge_succeeded"
    CHARGE_FAILED = "charge_failed"
    RELEASE_REQUESTED = "release_requested"
    RELEASED = "released"
    RELEASE_FAILED = "release_failed"
    REFUND_REQUESTED = "refund_requested"
    REFUNDED = "refunded"
    REFUND_FAILED = "refund_failed"
    FEE_EARNED = "fee_earned"


class LedgerEntry(Base):
    """Append-only money record (build plan §6). Afe never holds a balance; this is the
    record of instructions sent to, and confirmations received from, the partner."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenancy_id: Mapped[int] = mapped_column(ForeignKey("tenancies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount_pesewas: Mapped[int]
    partner_ref: Mapped[str] = mapped_column(String(120), default="", index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class OutboxEvent(Base):
    """Money events written in the same transaction as the change they describe, then
    published (Statement §8.7: payment and escrow events always reach Postgres first)."""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(index=True)


@event.listens_for(LedgerEntry, "before_update")
def _ledger_no_update(*_):
    raise PermissionError("The ledger is append-only")


@event.listens_for(LedgerEntry, "before_delete")
def _ledger_no_delete(*_):
    raise PermissionError("The ledger is append-only")


@event.listens_for(Session, "do_orm_execute")
def _ledger_no_bulk(state: ORMExecuteState):
    if (state.is_update or state.is_delete) and any(m.class_ is LedgerEntry for m in state.all_mappers):
        raise PermissionError("The ledger is append-only")


class PayeeChannel(StrEnum):
    MTN = "momo_mtn"
    TELECEL = "momo_telecel"
    AT = "momo_at"
    BANK = "bank"


class PayeeStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class Payee(Base):
    """Where a landlord's money goes. The account name must match their verified Ghana Card
    name, and a changed account only receives money after a cooling-off period."""

    __tablename__ = "payees"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(14))
    account_number: Mapped[str] = mapped_column(String(34))
    account_name: Mapped[str] = mapped_column(String(160), comment="As returned by the partner's name lookup")
    status: Mapped[str] = mapped_column(String(10), default=PayeeStatus.ACTIVE)
    usable_from: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    superseded_at: Mapped[datetime | None]

    @property
    def masked(self) -> str:
        return f"{self.channel.replace('momo_', '').upper()} ••••{self.account_number[-4:]}"


class DisputeStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (Index("ix_disputes_open", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenancy_id: Mapped[int] = mapped_column(ForeignKey("tenancies.id"), index=True)
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(40))
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=DisputeStatus.OPEN)
    decision: Mapped[str] = mapped_column(String(10), default="", comment="release | refund")
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    tenancy: Mapped[Tenancy] = relationship()
    opened_by: Mapped[User] = relationship(foreign_keys=[opened_by_id])
