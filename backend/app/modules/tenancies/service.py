"""Tenancies and protected payments (build plan Phase 2).

The rule the whole flow serves: money is held by a licensed partner and reaches the
landlord only when the tenant confirms move-in, a reviewer decides a dispute, or the
fallback rule applies (landlord evidence, no dispute, N days after move-in). Undelivered
homes are refunded. Every step writes the ledger and the outbox in the same transaction.
"""

import logging
import math
import re
import secrets
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import totp
from app.core.errors import DomainError, InvalidInput, NotAllowed, NotFound, RuleViolation
from app.core.ghana import format_ghs
from app.core.pdf import text_pdf
from app.db import utcnow
from app.modules.audit.log import record
from app.modules.compliance.service import charges_free, rule, rule_versions
from app.modules.enquiries.models import Viewing, ViewingStatus
from app.modules.identity.service import latest_check
from app.modules.listings.models import ListingStatus
from app.modules.media.storage import storage
from app.modules.notifications.service import notify, notify_admins
from app.modules.risk.flags import open_flags, raise_flag
from app.modules.risk.models import Severity
from app.modules.verification.service import current_verification

from .models import (
    ACTIVE,
    HOLDING,
    Dispute,
    DisputeStatus,
    LedgerEntry,
    LedgerKind,
    OutboxEvent,
    Payee,
    PayeeChannel,
    PayeeStatus,
    Tenancy,
    TenancyStatus,
)
from .partners import PartnerError, PartnerEvent, get_partner

MONEY_RULES = [
    "advance_cap_months_long", "advance_cap_months_short", "max_deposit_months", "protection_fee_bps",
    "protection_fee_payer", "refund_gateway_fee_bps", "offer_valid_hours", "move_in_grace_days",
    "auto_release_days", "pilot_max_tenancy_pesewas", "pilot_max_held_pesewas", "pilot_manual_release",
]


log = logging.getLogger("afe.tenancies")
# Admins are warned when the money held (or being collected) reaches this share of the pilot's limit.
CAP_WARNING = 0.8
# A refund or payout whose outcome is unknown (the partner call broke, not refused) waits for a person.
UNCONFIRMED = ("money.refund_unconfirmed", "money.release_unconfirmed")


def _money_alarm(db: Session, t: Tenancy, flag_rule: str, explanation: str) -> None:
    """A money exception: a high-severity flag for the money page, and admins told at once. Once while the flag
    is open, however often the job that found it runs again."""
    already = any(f.rule == flag_rule for f in open_flags(db, t))
    raise_flag(db, t, flag_rule, Severity.HIGH, explanation)
    if not already:
        notify_admins(db, "money_alert", link="/review/money", explanation=explanation, reference=t.reference)


def require_enabled() -> None:
    if not get_settings().protected_payments_enabled:
        raise RuleViolation("Protected payments aren't open yet. Never pay anyone outside Afe before you move in.")


def _ledger(db: Session, t: Tenancy, kind: LedgerKind, amount: int, partner_ref: str = "", **data) -> None:
    db.add(LedgerEntry(tenancy_id=t.id, kind=kind, amount_pesewas=amount, partner_ref=partner_ref, data=data))
    db.add(OutboxEvent(topic=f"tenancy.{kind}", payload={"tenancy": t.reference, "amount": amount, **data}))
    db.flush()


def _close(t: Tenancy, status: TenancyStatus, reason: str) -> None:
    t.status = status
    t.closed_at = utcnow()
    t.close_reason = reason[:300]


def get_by_reference(db: Session, reference: str, user=None, lock: bool = False) -> Tenancy:
    q = select(Tenancy).where(Tenancy.reference == reference.upper())
    if lock:
        q = q.with_for_update()
    t = db.scalar(q)
    if t is None or (user is not None and not user.can_review and user.id not in (t.tenant_id, t.landlord_id)):
        raise NotFound("Tenancy not found.")
    return t


def tenancies_for(db: Session, user) -> list[Tenancy]:
    return list(
        db.scalars(
            select(Tenancy)
            .where((Tenancy.tenant_id == user.id) | (Tenancy.landlord_id == user.id))
            .order_by(Tenancy.created_at.desc())
        )
    )


# --- Payout accounts -------------------------------------------------------------------------------


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^A-Z]+", (name or "").upper()) if len(t) > 1}


def names_match(verified: str, account: str) -> bool:
    """The wallet name must be the verified person: same names, or at least two names in
    common and nothing extra on the shorter one (e.g. a middle name missing)."""
    a, b = _tokens(verified), _tokens(account)
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return a == b or (len(small) >= 2 and small <= big)


def active_payee(db: Session, user) -> Payee | None:
    return db.scalar(select(Payee).where(Payee.user_id == user.id, Payee.status == PayeeStatus.ACTIVE))


def set_payee(db: Session, user, channel: str, account_number: str, code: str) -> Payee:
    """Add or change where a landlord's money goes. Needs a fresh authenticator code, the
    partner's name lookup must match the verified Ghana Card name, and a change only
    receives money after the cooling-off period (stops account-takeover payouts)."""
    if not user.is_lister:
        raise NotAllowed("Only landlords and agents have payout accounts.")
    if channel not in PayeeChannel.__members__.values():
        raise InvalidInput("Choose MTN MoMo, Telecel Cash, AT Money or a bank account.")
    account_number = re.sub(r"[\s-]", "", account_number or "")
    if not account_number.isdigit() or not 9 <= len(account_number) <= 20:
        raise InvalidInput("Enter the wallet number or account number, digits only.")
    if user.totp_enabled_at and not totp.verify(user.totp_secret, code):
        raise RuleViolation("That authenticator code is wrong. Changing where money goes needs a fresh code.")
    check = latest_check(db, user, passed_only=True)
    if check is None or current_verification(db, party=user) is None:
        raise RuleViolation("Verify your identity before adding a payout account.")
    try:
        account_name = get_partner().lookup_name(channel, account_number)
    except PartnerError as exc:
        raise RuleViolation(str(exc)) from exc
    if not names_match(check.name_on_card, account_name):
        raise RuleViolation(
            f"That account is registered to {account_name}, not to {check.name_on_card}. Use an account in your own name."
        )
    previous = active_payee(db, user)
    now = utcnow()
    if previous:
        if previous.channel == channel and previous.account_number == account_number:
            return previous
        previous.status, previous.superseded_at = PayeeStatus.SUPERSEDED, now
        db.flush()
    cooling = timedelta(hours=rule(db, "payee_cooling_off_hours")) if previous else timedelta(0)
    payee = Payee(user_id=user.id, channel=channel, account_number=account_number, account_name=account_name,
                  usable_from=now + cooling)
    db.add(payee)
    db.flush()
    record(db, user, "payee.set", payee, channel=channel, last4=account_number[-4:], changed=previous is not None)
    if previous:
        # Security alert on every channel: if this wasn't them, they have the cooling-off time to act.
        notify(db, user, "payee_changed", link="/landlord/payouts", account=payee.masked,
               when=payee.usable_from.strftime("%a %d %b %H:%M"))
    return payee


# --- Offers ------------------------------------------------------------------------------------------------


def quote(db: Session, rent: int, advance: int, deposit: int) -> dict:
    held = rent * (advance + deposit)
    fee = 0 if charges_free(db) else math.ceil(held * rule(db, "protection_fee_bps") / 10_000)
    payer = rule(db, "protection_fee_payer")
    tenant_share = {"tenant": fee, "landlord": 0, "split": math.ceil(fee / 2)}[payer]
    return {"held": held, "fee": fee, "payer": payer, "charge": held + tenant_share, "payout": held - (fee - tenant_share)}


def make_offer(db: Session, landlord, viewing: Viewing, move_in_date: date, lease_months: int, advance_months: int,
               deposit_months: int) -> Tenancy:
    require_enabled()
    if viewing.lister_id != landlord.id:
        raise NotFound("Viewing not found.")
    if viewing.status != ViewingStatus.COMPLETED:
        raise RuleViolation("You can offer a tenancy only after the renter has viewed the home.")
    listing = viewing.listing
    if listing.status != ListingStatus.LIVE:
        raise RuleViolation("The listing must be live to offer a tenancy.")
    if current_verification(db, party=landlord) is None or current_verification(db, unit=listing.unit) is None:
        raise RuleViolation("You and the home must both be verified to offer a tenancy.")
    payee = active_payee(db, landlord)
    if payee is None:
        raise RuleViolation("Add a payout account before offering a tenancy.")
    today = utcnow().date()
    if not today <= move_in_date <= today + timedelta(days=120):
        raise InvalidInput("Choose a move-in date within the next four months.")
    if not 1 <= lease_months <= 60:
        raise InvalidInput("The lease must be between 1 and 60 months.")
    cap = rule(db, "advance_cap_months_long" if lease_months > 6 else "advance_cap_months_short")
    if not 0 <= advance_months <= cap:
        raise RuleViolation(
            f"The law caps advance rent at {cap} months for a {lease_months}-month tenancy. "
            f"Afe can't hold more than that."
        )
    if not 0 <= deposit_months <= rule(db, "max_deposit_months"):
        raise RuleViolation(f"The deposit can be at most {rule(db, 'max_deposit_months')} months' rent.")
    if advance_months + deposit_months == 0:
        raise InvalidInput("There is nothing to hold: add advance rent or a deposit.")
    q = quote(db, listing.rent_pesewas, advance_months, deposit_months)
    if q["held"] > rule(db, "pilot_max_tenancy_pesewas"):
        raise RuleViolation(
            f"During the pilot Afe holds at most {format_ghs(rule(db, 'pilot_max_tenancy_pesewas'))} per tenancy."
        )
    t = Tenancy(
        reference=f"AFE-T-{secrets.token_hex(3).upper()}", listing_id=listing.id, unit_id=listing.unit_id,
        landlord_id=landlord.id, tenant_id=viewing.renter_id, viewing_id=viewing.id, payee_id=payee.id,
        rent_pesewas=listing.rent_pesewas, advance_months=advance_months, deposit_months=deposit_months,
        lease_months=lease_months, move_in_date=move_in_date, held_pesewas=q["held"], fee_pesewas=q["fee"],
        fee_payer=q["payer"], charge_pesewas=q["charge"], payout_pesewas=q["payout"],
        rule_versions=rule_versions(db, MONEY_RULES),
        offer_expires_at=utcnow() + timedelta(hours=rule(db, "offer_valid_hours")),
    )
    try:
        with db.begin_nested():
            db.add(t)
            db.flush()
    except IntegrityError as exc:
        raise RuleViolation("This home already has a tenancy in progress.") from exc
    record(db, landlord, "tenancy.offered", t, held=t.held_pesewas, rules=t.rule_versions)
    notify(db, t.tenant, "tenancy_offered", link=f"/tenancies/{t.reference}", landlord=landlord.name,
           listing=listing.title, amount=format_ghs(t.charge_pesewas))
    return t


def decline(db: Session, tenant, t: Tenancy) -> Tenancy:
    if t.tenant_id != tenant.id:
        raise NotFound("Tenancy not found.")
    if t.status != TenancyStatus.OFFERED:
        raise RuleViolation("Only an open offer can be declined.")
    _close(t, TenancyStatus.DECLINED, "Declined by the tenant")
    db.flush()
    record(db, tenant, "tenancy.declined", t)
    return t


def withdraw(db: Session, landlord, t: Tenancy) -> Tenancy:
    if t.landlord_id != landlord.id:
        raise NotFound("Tenancy not found.")
    if t.status != TenancyStatus.OFFERED:
        raise RuleViolation("You can only withdraw an offer the tenant hasn't paid.")
    _close(t, TenancyStatus.WITHDRAWN, "Withdrawn by the landlord")
    db.flush()
    record(db, landlord, "tenancy.withdrawn", t)
    return t


def held_total(db: Session) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(Tenancy.held_pesewas), 0)).where(
            Tenancy.status.in_([str(s) for s in (*HOLDING, TenancyStatus.FUNDING)])
        )
    )


def agreement_text(t: Tenancy) -> list[str]:
    unit = t.unit
    return [
        f"Reference: {t.reference}. Created through Afe on {utcnow():%d %B %Y}.",
        f"Landlord: {t.landlord.name}. Tenant: {t.tenant.name}.",
        f"Home: {unit.digital_address}, {unit.unit_label}, {unit.area.name}, {unit.area.city}.",
        f"Monthly rent: {format_ghs(t.rent_pesewas)}. Lease: {t.lease_months} months from {t.move_in_date:%d %B %Y}.",
        f"Advance rent: {t.advance_months} months. Deposit: {t.deposit_months} months. "
        f"Total held by Afe's payment partner: {format_ghs(t.held_pesewas)}.",
        (f"Afe protection fee: {format_ghs(t.fee_pesewas)}, paid by the {t.fee_payer}. " if t.fee_pesewas
         else "No Afe protection fee: launch offer. ") +
        f"The tenant pays {format_ghs(t.charge_pesewas)}; the landlord receives {format_ghs(t.payout_pesewas)} on release.",
        "How the money is protected: the payment is held by Afe's licensed payment partner, not by Afe and not by "
        "the landlord. It is released to the landlord when the tenant confirms they have moved in. If either side "
        "raises a problem before release, Afe reviews the evidence and decides whether to release or refund. If the "
        "home is not delivered, the tenant is refunded, less the payment partner's charges.",
        "This summary records the terms agreed on Afe. It does not replace a full written tenancy agreement under the "
        "Rent Act, 1963 (Act 220), which both parties should sign.",
    ]


def accept(db: Session, tenant, t: Tenancy) -> Tenancy:
    """The tenant accepts the terms; they're written into the agreement and a checkout opens."""
    require_enabled()
    if t.tenant_id != tenant.id:
        raise NotFound("Tenancy not found.")
    if t.status == TenancyStatus.FUNDING and t.checkout_url:
        return t  # a second tap goes back to the same checkout
    if t.status != TenancyStatus.OFFERED:
        raise RuleViolation("This offer is no longer open.")
    if t.offer_expires_at <= utcnow():
        _close(t, TenancyStatus.EXPIRED, "Offer expired")
        db.flush()
        raise RuleViolation("This offer has expired. Ask the landlord for a new one.")
    held_before, limit = held_total(db), rule(db, "pilot_max_held_pesewas")
    if held_before + t.held_pesewas > limit:
        raise RuleViolation("Afe's protected payments are full for now during the pilot. Try again in a few days.")
    t.agreement_key = storage.save("private", "agreements", text_pdf(f"Afe tenancy summary {t.reference}", agreement_text(t)), ".pdf")
    try:
        t.checkout_url = get_partner().create_charge(
            t.reference, t.charge_pesewas, tenant.phone or "", tenant.email or "",
            f"{get_settings().frontend_url}/tenancies/{t.reference}",
        )
    except PartnerError as exc:
        raise RuleViolation(f"Payment could not start: {exc}. Try again shortly.") from exc
    t.status, t.accepted_at = TenancyStatus.FUNDING, utcnow()
    db.flush()
    _ledger(db, t, LedgerKind.CHARGE_STARTED, t.charge_pesewas)
    record(db, tenant, "tenancy.accepted", t)
    if held_before < limit * CAP_WARNING <= held_before + t.held_pesewas:
        notify_admins(db, "money_cap", link="/review/money", held=format_ghs(held_before + t.held_pesewas),
                      limit=format_ghs(limit))
    return t


# --- Partner confirmations ----------------------------------------------------------------------------


def apply_partner_event(db: Session, ev: PartnerEvent) -> Tenancy | None:
    """Idempotent: partners resend confirmations, and a resend must change nothing."""
    t = db.scalar(select(Tenancy).where(Tenancy.reference == ev.reference).with_for_update())
    if t is None:
        return None
    if ev.partner_ref and db.scalar(
        select(LedgerEntry.id).where(LedgerEntry.tenancy_id == t.id, LedgerEntry.partner_ref == ev.partner_ref,
                                     LedgerEntry.kind.in_(["charge_succeeded", "charge_failed", "released",
                                                           "release_failed", "refunded", "refund_failed"]))
    ):
        return t

    if ev.kind == "charge.succeeded" and t.status in (TenancyStatus.FUNDING, TenancyStatus.OFFERED, TenancyStatus.EXPIRED):
        if ev.amount_pesewas != t.charge_pesewas:
            _ledger(db, t, LedgerKind.CHARGE_FAILED, ev.amount_pesewas, ev.partner_ref, note="amount mismatch")
            _money_alarm(db, t, "money.amount_mismatch",
                         f"Partner reported {format_ghs(ev.amount_pesewas)}; expected {format_ghs(t.charge_pesewas)}.")
            return t
        if t.status == TenancyStatus.EXPIRED:
            # Paid after the offer lapsed: the money is held but the home may be gone. A person decides.
            _money_alarm(db, t, "money.paid_after_expiry", "Tenant paid after the offer expired.")
        t.status, t.funded_at = TenancyStatus.FUNDED, utcnow()
        t.listing.status = ListingStatus.LET
        t.listing.status_reason = f"Let through Afe ({t.reference})"
        db.flush()
        _ledger(db, t, LedgerKind.CHARGE_SUCCEEDED, ev.amount_pesewas, ev.partner_ref)
        notify(db, t.tenant, "tenancy_funded_tenant", link=f"/tenancies/{t.reference}",
               amount=format_ghs(t.charge_pesewas), when=t.move_in_date.strftime("%d %b"))
        notify(db, t.landlord, "tenancy_funded_landlord", link=f"/tenancies/{t.reference}", tenant=t.tenant.name,
               amount=format_ghs(t.held_pesewas), when=t.move_in_date.strftime("%d %b"))
    elif ev.kind == "charge.failed" and t.status == TenancyStatus.FUNDING:
        t.status = TenancyStatus.OFFERED
        db.flush()
        _ledger(db, t, LedgerKind.CHARGE_FAILED, ev.amount_pesewas, ev.partner_ref)
    elif ev.kind == "release.succeeded" and t.status == TenancyStatus.RELEASING:
        _mark_released(db, t, ev.partner_ref)
    elif ev.kind == "release.failed" and t.status == TenancyStatus.RELEASING:
        t.status = TenancyStatus.RELEASE_PENDING
        db.flush()
        _ledger(db, t, LedgerKind.RELEASE_FAILED, ev.amount_pesewas, ev.partner_ref)
        _money_alarm(db, t, "money.release_failed", "The partner could not pay the landlord.")
    elif ev.kind == "refund.succeeded" and t.status == TenancyStatus.REFUNDING:
        _mark_refunded(db, t, ev.amount_pesewas, ev.partner_ref)
    elif ev.kind == "refund.failed" and t.status == TenancyStatus.REFUNDING:
        _ledger(db, t, LedgerKind.REFUND_FAILED, ev.amount_pesewas, ev.partner_ref)
        _money_alarm(db, t, "money.refund_failed", "The partner could not refund the tenant.")
    return t


def _mark_released(db: Session, t: Tenancy, partner_ref: str) -> None:
    _close(t, TenancyStatus.RELEASED, "Paid to the landlord")
    db.flush()
    _ledger(db, t, LedgerKind.RELEASED, t.payout_pesewas, partner_ref)
    _ledger(db, t, LedgerKind.FEE_EARNED, t.fee_pesewas)
    notify(db, t.landlord, "tenancy_released", link=f"/tenancies/{t.reference}", amount=format_ghs(t.payout_pesewas),
           account=t.payee.masked)
    notify(db, t.tenant, "tenancy_review_invite", link=f"/tenancies/{t.reference}", landlord=t.landlord.name)
    from app.modules.rentals.service import from_afe_tenancy

    from_afe_tenancy(db, t)


def _mark_refunded(db: Session, t: Tenancy, amount: int, partner_ref: str) -> None:
    _close(t, TenancyStatus.REFUNDED, t.close_reason or "Refunded to the tenant")
    if t.listing.status == ListingStatus.LET:
        t.listing.status = ListingStatus.PAUSED
        t.listing.status_reason = "Tenancy refunded. Send the listing for review to relist."
    db.flush()
    _ledger(db, t, LedgerKind.REFUNDED, amount, partner_ref)
    notify(db, t.tenant, "tenancy_refunded", link=f"/tenancies/{t.reference}", amount=format_ghs(amount))


# --- Release and refund ----------------------------------------------------------------------------------


def _request_release(db: Session, t: Tenancy, actor, reason: str, reviewer_decided: bool = False) -> Tenancy:
    """Pilot: a reviewer approves every release. Always: a payout account inside its
    cooling-off period waits for a reviewer."""
    payee_ready = (t.payee.status == PayeeStatus.ACTIVE and t.payee.usable_from <= utcnow()
                   and t.landlord.is_active)
    if not payee_ready or (rule(db, "pilot_manual_release") and not reviewer_decided):
        t.status = TenancyStatus.RELEASE_PENDING
        t.close_reason = reason
        db.flush()
        record(db, actor, "tenancy.release_pending", t, reason=reason, payee_ready=payee_ready)
        return t
    return _send_release(db, t, actor, reason)


def _send_release(db: Session, t: Tenancy, actor, reason: str) -> Tenancy:
    if not t.landlord.is_active:
        raise RuleViolation("The landlord's account is suspended. Restore it before releasing money to them.")
    if t.payee.status != PayeeStatus.ACTIVE or t.payee.usable_from > utcnow():
        # The landlord changed accounts since the offer: pay the account they have now, once it's usable.
        current = active_payee(db, t.landlord)
        if current is None or current.usable_from > utcnow():
            raise RuleViolation("The landlord's payout account is still in its cooling-off period.")
        t.payee_id = current.id
        db.flush()
        db.refresh(t)
    try:
        transfer = get_partner().release(t.reference, t.payout_pesewas, t.payee.channel, t.payee.account_number)
    except PartnerError as exc:
        raise RuleViolation(f"The partner refused the payout: {exc}") from exc
    t.status = TenancyStatus.RELEASING
    db.flush()
    _ledger(db, t, LedgerKind.RELEASE_REQUESTED, t.payout_pesewas, transfer.ref, reason=reason)
    record(db, actor, "tenancy.release_sent", t, reason=reason)
    if transfer.completed:
        _mark_released(db, t, transfer.ref)
    return t


def _send_refund(db: Session, t: Tenancy, actor, reason: str) -> Tenancy:
    # Tenancies paid during the launch offer are refunded in full: Afe absorbs the gateway's charge.
    free = t.funded_at is not None and charges_free(db, t.funded_at.date())
    keep = 0 if free else math.ceil(t.held_pesewas * rule(db, "refund_gateway_fee_bps") / 10_000)
    amount = max(t.charge_pesewas - keep, 0)
    try:
        transfer = get_partner().refund(t.reference, amount)
    except PartnerError as exc:
        raise RuleViolation(f"The partner refused the refund: {exc}") from exc
    t.status, t.close_reason = TenancyStatus.REFUNDING, reason
    db.flush()
    _ledger(db, t, LedgerKind.REFUND_REQUESTED, amount, transfer.ref, reason=reason)
    record(db, actor, "tenancy.refund_sent", t, reason=reason, amount=amount)
    if transfer.completed:
        _mark_refunded(db, t, amount, transfer.ref)
    return t


def confirm_move_in(db: Session, tenant, t: Tenancy, photo: bytes | None = None) -> Tenancy:
    if t.tenant_id != tenant.id:
        raise NotFound("Tenancy not found.")
    if t.status != TenancyStatus.FUNDED:
        raise RuleViolation("There's nothing to confirm on this tenancy right now.")
    if photo:
        from app.modules.media.images import process_photo

        # Re-encoded with location and camera data removed; kept private as dispute evidence.
        t.move_in_photo_key = storage.save("private", "move-in", process_photo(photo).webp, ".webp")
    t.tenant_confirmed_at = utcnow()
    db.flush()
    record(db, tenant, "tenancy.move_in_confirmed", t)
    return _request_release(db, t, tenant, "Tenant confirmed move-in")


def record_landlord_evidence(db: Session, landlord, t: Tenancy, note: str) -> Tenancy:
    if t.landlord_id != landlord.id:
        raise NotFound("Tenancy not found.")
    if t.status != TenancyStatus.FUNDED:
        raise RuleViolation("You can record move-in only while the payment is held.")
    if t.move_in_date > utcnow().date():
        raise RuleViolation("Record the move-in on or after the move-in date.")
    if len(note.strip()) < 10:
        raise InvalidInput("Say what happened: when you handed over the keys, and who was there.")
    t.landlord_evidence, t.landlord_evidence_at = note.strip()[:2000], utcnow()
    db.flush()
    record(db, landlord, "tenancy.landlord_evidence", t)
    return t


def approve_release(db: Session, reviewer, t: Tenancy, note: str = "") -> Tenancy:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can approve releases.")
    if t.status != TenancyStatus.RELEASE_PENDING:
        raise RuleViolation("This tenancy isn't waiting for a release approval.")
    return _send_release(db, t, reviewer, f"Approved by a reviewer. {note}".strip())


# --- Disputes ------------------------------------------------------------------------------------------------

DISPUTE_REASONS = {
    "not_delivered": "The home wasn't handed over",
    "not_as_listed": "The home isn't what was listed",
    "tenant_no_show": "The tenant didn't move in",
    "access_refused": "Access was refused on the move-in date",
    "other": "Something else",
}


def open_dispute(db: Session, user, t: Tenancy, reason: str, details: str) -> Dispute:
    if user.id not in (t.tenant_id, t.landlord_id):
        raise NotFound("Tenancy not found.")
    if t.status not in (TenancyStatus.FUNDED, TenancyStatus.RELEASE_PENDING):
        raise RuleViolation("You can raise a problem only while the payment is held.")
    if reason not in DISPUTE_REASONS:
        raise InvalidInput("Choose what went wrong.")
    if len(details.strip()) < 20:
        raise InvalidInput("Describe what happened in a few sentences. A reviewer will read it.")
    dispute = Dispute(tenancy_id=t.id, opened_by_id=user.id, reason=reason, details=details.strip()[:4000])
    t.status = TenancyStatus.DISPUTED
    db.add(dispute)
    db.flush()
    record(db, user, "tenancy.disputed", t, reason=reason)
    other = t.landlord if user.id == t.tenant_id else t.tenant
    for person in (t.tenant, t.landlord):
        notify(db, person, "dispute_opened", link=f"/tenancies/{t.reference}", opener=user.name if person is other else "You",
               reference=t.reference)
    return dispute


def resolve_dispute(db: Session, reviewer, dispute: Dispute, decision: str, note: str) -> Dispute:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can decide disputes.")
    if dispute.status != DisputeStatus.OPEN:
        raise RuleViolation("This dispute is already decided.")
    if decision not in ("release", "refund"):
        raise InvalidInput("Decide release or refund.")
    if len(note.strip()) < 10:
        raise InvalidInput("Explain the decision; both sides will see it.")
    t = dispute.tenancy
    if reviewer.id in (t.tenant_id, t.landlord_id):
        raise RuleViolation("You can't decide a dispute you're part of.")
    dispute.status, dispute.decision = DisputeStatus.RESOLVED, decision
    dispute.decided_by_id, dispute.decided_at, dispute.decision_note = reviewer.id, utcnow(), note.strip()[:500]
    t.status = TenancyStatus.FUNDED
    db.flush()
    record(db, reviewer, "tenancy.dispute_resolved", dispute, decision=decision, note=note)
    if decision == "release":
        _request_release(db, t, reviewer, f"Dispute decided for the landlord: {note}", reviewer_decided=True)
    else:
        _send_refund(db, t, reviewer, f"Dispute decided for the tenant: {note}")
    return dispute


def open_disputes(db: Session) -> list[Dispute]:
    return list(db.scalars(select(Dispute).where(Dispute.status == DisputeStatus.OPEN).order_by(Dispute.created_at)))


def dispute_for(db: Session, t: Tenancy) -> Dispute | None:
    return db.scalar(select(Dispute).where(Dispute.tenancy_id == t.id).order_by(Dispute.id.desc()))


# --- Scheduled work --------------------------------------------------------------------------------------------


def run_due(db: Session, today: date | None = None) -> dict[str, int]:
    """Run every few minutes (cron or Celery beat): expire offers, refund undelivered homes,
    and apply the move-in fallback rule (decision B8)."""
    today = today or utcnow().date()
    now = utcnow()
    counts = {"expired": 0, "refunded": 0, "released": 0, "failed": 0}
    for t in db.scalars(select(Tenancy).where(Tenancy.status == TenancyStatus.OFFERED, Tenancy.offer_expires_at <= now)):
        _close(t, TenancyStatus.EXPIRED, "Offer expired")
        counts["expired"] += 1
    for t in db.scalars(
        select(Tenancy).where(Tenancy.status == TenancyStatus.FUNDING, Tenancy.offer_expires_at <= now - timedelta(days=1))
    ):
        _close(t, TenancyStatus.EXPIRED, "Checkout not completed")
        counts["expired"] += 1
    grace = timedelta(days=rule(db, "move_in_grace_days"))
    fallback = timedelta(days=rule(db, "auto_release_days"))
    for t in list(db.scalars(select(Tenancy).where(Tenancy.status == TenancyStatus.FUNDED))):
        refund = t.landlord_evidence_at is None and today > t.move_in_date + grace
        release = t.landlord_evidence_at is not None and today >= t.move_in_date + fallback
        if not (refund or release) or any(f.rule in UNCONFIRMED for f in open_flags(db, t)):
            continue
        try:
            with db.begin_nested():  # a failed payout mustn't undo the rest of this run, or stop it
                if refund:
                    _send_refund(db, t, None, "Home not delivered by the move-in date")
                else:
                    _request_release(db, t, None, "Landlord evidence and no dispute after the move-in period")
        except DomainError as exc:  # the partner refused: nothing moved, so it's tried again next run
            _money_alarm(db, t, "money.refund_failed" if refund else "money.release_failed", str(exc))
            counts["failed"] += 1
            continue
        except Exception as exc:  # noqa: BLE001 - the outcome is unknown: never repeat it without a person
            log.exception("run_due: %s for %s", "refund" if refund else "release", t.reference)
            _money_alarm(db, t, UNCONFIRMED[0] if refund else UNCONFIRMED[1],
                         f"The partner didn't confirm the {'refund' if refund else 'payout'} ({type(exc).__name__}). "
                         "Check with the partner before retrying: Afe won't try it again until this flag is resolved.")
            counts["failed"] += 1
            continue
        counts["refunded" if refund else "released"] += 1
    db.flush()
    return counts


# --- Finance ---------------------------------------------------------------------------------------------------


def finance_summary(db: Session) -> dict:
    rows = db.execute(
        select(Tenancy.status, func.count(), func.coalesce(func.sum(Tenancy.held_pesewas), 0)).group_by(Tenancy.status)
    ).all()
    by = {status: {"count": n, "held_pesewas": held} for status, n, held in rows}
    earned = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_pesewas), 0)).where(LedgerEntry.kind == LedgerKind.FEE_EARNED)
    )
    return {"by_status": by, "held_now_pesewas": held_total(db), "fees_earned_pesewas": earned}


def reconcile(db: Session) -> list[dict]:
    """Compare Afe's ledger with the partner's statement (nightly). Every difference is an
    exception for the finance view; the target is zero."""
    kinds = {"charge_succeeded": "charge", "released": "release", "refunded": "refund"}
    ours = {
        (e.partner_ref, kinds[e.kind]): e
        for e in db.scalars(select(LedgerEntry).where(LedgerEntry.kind.in_(list(kinds)), LedgerEntry.partner_ref != ""))
    }
    theirs = {(line.partner_ref, line.kind): line for line in get_partner().statement()}
    exceptions = []
    for key, entry in ours.items():
        line = theirs.get(key)
        tenancy = db.get(Tenancy, entry.tenancy_id)
        if line is None:
            exceptions.append({"partner_ref": key[0], "kind": key[1], "problem": "In Afe's ledger, not in the partner's statement",
                               "tenancy": tenancy.reference, "ours": entry.amount_pesewas, "theirs": None})
        elif line.amount_pesewas != entry.amount_pesewas:
            exceptions.append({"partner_ref": key[0], "kind": key[1], "problem": "Amounts differ",
                               "tenancy": tenancy.reference, "ours": entry.amount_pesewas, "theirs": line.amount_pesewas})
    for key, line in theirs.items():
        if key not in ours:
            exceptions.append({"partner_ref": key[0], "kind": key[1], "problem": "In the partner's statement, not in Afe's ledger",
                               "tenancy": line.reference, "ours": None, "theirs": line.amount_pesewas})
    return exceptions


def nightly_reconcile(db: Session) -> list[dict]:
    """The nightly job: reconcile, and tell admins about any difference the same morning."""
    problems = reconcile(db)
    if problems:
        first = problems[0]
        notify_admins(db, "money_reconcile", link="/review/money", count=len(problems),
                      example=f"{first['tenancy']} {first['kind']}: {first['problem']}")
    return problems


def publish_outbox(db: Session, limit: int = 500) -> int:
    """Mark outbox events as published. The broker (Redis Streams, plan §8) plugs in here;
    until then events are logged and marked, so nothing piles up unseen."""
    rows = list(db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.id).limit(limit)))
    for row in rows:
        row.published_at = utcnow()
    db.flush()
    return len(rows)


def is_active(t: Tenancy) -> bool:
    return t.status in ACTIVE


def receipt_lines(db: Session, t: Tenancy, user) -> list[tuple[str, int, str, str]]:
    """What this person paid or received, from the ledger: (what, amount, when, partner ref)."""
    mine = {"charge_succeeded": "Paid into protection", "refunded": "Refunded to you"} if user.id == t.tenant_id else \
        {"released": "Paid to you"}
    rows = db.scalars(select(LedgerEntry).where(LedgerEntry.tenancy_id == t.id).order_by(LedgerEntry.id))
    return [(mine[e.kind], e.amount_pesewas, f"{e.created_at:%d %b %Y %H:%M}", e.partner_ref) for e in rows if e.kind in mine]


def receipt_pdf(db: Session, t: Tenancy, user) -> bytes:
    from app.modules.documents.render import tenancy_receipt

    lines = receipt_lines(db, t, user)
    if not lines:
        raise NotFound("There's no payment on this tenancy yet.")
    return tenancy_receipt(db, t, user, lines)


def pilot_report(db: Session) -> dict:
    """The founder's daily view of the money during the pilot (build plan §6): what's held
    against the pilot limit, what happened in the last day, and anything that needs a person."""
    from app.modules.risk.models import FlagStatus, RiskFlag

    since = utcnow() - timedelta(days=1)
    moved = dict(db.execute(
        select(LedgerEntry.kind, func.count()).where(LedgerEntry.created_at > since).group_by(LedgerEntry.kind)
    ).all())
    money_flags = db.scalar(select(func.count()).select_from(RiskFlag).where(
        RiskFlag.rule.like("money.%"), RiskFlag.status == FlagStatus.OPEN))
    return {
        "held_pesewas": held_total(db),
        "limit_pesewas": rule(db, "pilot_max_held_pesewas"),
        "funded_today": moved.get(LedgerKind.CHARGE_SUCCEEDED, 0),
        "released_today": moved.get(LedgerKind.RELEASED, 0),
        "refunded_today": moved.get(LedgerKind.REFUNDED, 0),
        "releases_waiting": db.scalar(select(func.count()).select_from(Tenancy).where(
            Tenancy.status == TenancyStatus.RELEASE_PENDING)),
        "disputes_open": db.scalar(select(func.count()).select_from(Dispute).where(Dispute.status == DisputeStatus.OPEN)),
        "money_flags_open": money_flags,
        "reconcile_differences": len(reconcile(db)),
    }


def send_pilot_report(db: Session) -> dict | None:
    """Daily, while protected payments are on: send the report to every active admin."""
    from app.modules.accounts.models import Role, User
    from app.modules.notifications.service import notify_on

    if not get_settings().protected_payments_enabled:
        return None
    r = pilot_report(db)
    attention = r["releases_waiting"] + r["disputes_open"] + r["money_flags_open"] + r["reconcile_differences"]
    for admin in db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))):
        notify_on(
            db, admin, "pilot_report", {"in_app", "email", "sms"}, link="/review/money",
            held=format_ghs(r["held_pesewas"]), limit=format_ghs(r["limit_pesewas"]), funded=r["funded_today"],
            released=r["released_today"], refunded=r["refunded_today"], attention=attention,
            differences=r["reconcile_differences"],
        )
    return r
