"""Data rights under the Data Protection Act, 2012 (Act 843): a person can download what Afe
holds about them, and close their account.

Closing an account removes what can be removed and keeps what the law or fraud prevention
needs, with the name replaced by a reference:
- removed: profile, phone, email, password, authenticator, saved homes, notifications, sign-ins,
  message text, Ghana Card name;
- kept: the audit log, the money ledger and tenancies (financial records), verification
  decisions and the Ghana Card hash (so a banned person can't return with the same card),
  and documents behind a home's verification, for the retention period in the privacy notice.

An account under a fraud review, or with money held for it, can't be closed until that ends."""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core import totp
from app.core.errors import RuleViolation
from app.core.security import verify_password
from app.db import utcnow
from app.modules.audit.log import record

from .models import LISTER_ROLES, RefreshToken, Role, User

CLOSED_MESSAGE = "[Message removed when the account was closed]"
# Bump when the privacy notice or terms change in substance; people then accept again.
NOTICE_VERSION = "2026-09"


def accept_notice(db: Session, user: User) -> User:
    user.privacy_version, user.privacy_accepted_at = NOTICE_VERSION, utcnow()
    db.flush()
    record(db, user, "account.privacy_accepted", user, version=NOTICE_VERSION)
    return user


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def export_data(db: Session, user: User) -> dict:
    """Everything Afe holds about this person, in plain JSON. Identity numbers stay masked."""
    from app.modules.billing.models import Payment
    from app.modules.enquiries.models import Message, SavedListing, Thread, Viewing
    from app.modules.identity.models import IdentityCheck
    from app.modules.listings.models import Listing
    from app.modules.notifications.models import Notification
    from app.modules.reviews.models import Review
    from app.modules.tenancies.models import Payee, Tenancy
    from app.modules.units.models import Unit

    threads = list(db.scalars(select(Thread).where((Thread.renter_id == user.id) | (Thread.lister_id == user.id))))
    record(db, user, "account.data_exported", user)
    return {
        "exported_at": utcnow().isoformat(),
        "account": {
            "username": user.username, "name": user.display_name, "phone": user.phone, "email": user.email,
            "role": user.role, "created_at": _iso(user.created_at), "whatsapp_updates": user.whatsapp_opt_in,
            "whatsapp_opted_in_at": _iso(user.whatsapp_opt_in_at), "whatsapp_opt_in_source": user.whatsapp_opt_in_source,
            "whatsapp_opted_out_at": _iso(user.whatsapp_opt_out_at),
            "authenticator_on": bool(user.totp_enabled_at),
        },
        "identity_checks": [
            {"date": _iso(c.created_at), "provider": c.provider, "status": c.status, "card": c.masked_card,
             "name_on_card": c.name_on_card, "name_matches": c.name_matches, "liveness_passed": c.liveness_passed}
            for c in db.scalars(select(IdentityCheck).where(IdentityCheck.user_id == user.id))
        ],
        "homes": [
            {"address": u.digital_address, "unit": u.unit_label, "area": u.area.name, "bedrooms": u.bedrooms}
            for u in db.scalars(select(Unit).where(Unit.registered_by_id == user.id))
        ],
        "listings": [
            {"reference": li.reference, "title": li.title, "rent_pesewas": li.rent_pesewas, "status": li.status}
            for li in db.scalars(select(Listing).where(Listing.lister_id == user.id))
        ],
        "saved_homes": [
            s.listing.reference for s in db.scalars(select(SavedListing).where(SavedListing.user_id == user.id))
        ],
        "conversations": [
            {"listing": t.listing.reference, "messages": [
                {"from_you": m.sender_id == user.id, "at": _iso(m.created_at), "text": m.body}
                for m in db.scalars(select(Message).where(Message.thread_id == t.id).order_by(Message.id))
                if m.sender_id is not None
            ]}
            for t in threads
        ],
        "viewings": [
            {"listing": v.listing.reference, "when": _iso(v.requested_for), "status": v.status}
            for v in db.scalars(select(Viewing).where((Viewing.renter_id == user.id) | (Viewing.lister_id == user.id)))
        ],
        "payments": [
            {"reference": p.reference, "purpose": p.purpose, "amount_pesewas": p.amount_pesewas, "status": p.status,
             "date": _iso(p.created_at)}
            for p in db.scalars(select(Payment).where(Payment.user_id == user.id))
        ],
        "tenancies": [
            {"reference": t.reference, "you_are": "tenant" if t.tenant_id == user.id else "landlord",
             "status": t.status, "held_pesewas": t.held_pesewas, "move_in": t.move_in_date.isoformat()}
            for t in db.scalars(select(Tenancy).where((Tenancy.tenant_id == user.id) | (Tenancy.landlord_id == user.id)))
        ],
        "payout_accounts": [
            {"account": p.masked, "name": p.account_name, "status": p.status}
            for p in db.scalars(select(Payee).where(Payee.user_id == user.id))
        ],
        "reviews_written": [
            {"rating": r.rating, "text": r.body, "date": _iso(r.created_at)}
            for r in db.scalars(select(Review).where(Review.author_id == user.id))
        ],
        "notifications": [
            {"channel": n.channel, "title": n.title, "text": n.body, "date": _iso(n.created_at)}
            for n in db.scalars(
                select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(500)
            )
        ],
        "devices": [
            {"device": t.device, "signed_in": _iso(t.created_at)}
            for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)))
        ],
    }


def _closing_blockers(db: Session, user: User) -> list[str]:
    from app.modules.detection.models import DetectionLabel
    from app.modules.risk.models import FlagStatus, RiskFlag
    from app.modules.tenancies.models import HOLDING, Tenancy, TenancyStatus

    reasons = []
    live = [str(s) for s in (*HOLDING, TenancyStatus.OFFERED, TenancyStatus.FUNDING)]
    if db.scalar(select(Tenancy.id).where((Tenancy.tenant_id == user.id) | (Tenancy.landlord_id == user.id),
                                          Tenancy.status.in_(live))):
        reasons.append("You have a tenancy in progress. It must finish or be cancelled first.")
    under_review = db.scalar(select(RiskFlag.id).where(RiskFlag.subject_type == "users",
                                                       RiskFlag.subject_id == str(user.id),
                                                       RiskFlag.status.in_([FlagStatus.OPEN, FlagStatus.CONFIRMED])))
    fraud = db.scalar(select(DetectionLabel.id).where(DetectionLabel.subject_type == "users",
                                                      DetectionLabel.subject_id == str(user.id),
                                                      DetectionLabel.outcome == "fraud"))
    if under_review or fraud:
        reasons.append("Your account is being reviewed by Afe's trust team. Contact Afe to close it.")
    if user.role not in (*LISTER_ROLES, Role.RENTER):
        reasons.append("Staff accounts are closed by an Afe admin.")
    return reasons


def close_account(db: Session, user: User, confirm: str, password: str = "", code: str = "") -> None:
    if confirm.strip().upper() != "DELETE":
        raise RuleViolation('Type DELETE to confirm.')
    if user.totp_enabled_at:
        if not totp.verify(user.totp_secret, code):
            raise RuleViolation("That authenticator code is wrong.")
    elif user.password_hash and not verify_password(password, user.password_hash):
        raise RuleViolation("That password is wrong.")
    blockers = _closing_blockers(db, user)
    if blockers:
        raise RuleViolation(" ".join(blockers))

    from app.modules.enquiries.models import Message, SavedListing
    from app.modules.identity.models import IdentityCheck
    from app.modules.listings.models import ACTIVE_STATUSES, Listing, ListingStatus
    from app.modules.notifications.models import Notification
    from app.modules.tenancies.models import Payee

    now = utcnow()
    for listing in db.scalars(select(Listing).where(Listing.lister_id == user.id,
                                                    Listing.status.in_([str(s) for s in ACTIVE_STATUSES]))):
        listing.status, listing.status_reason = ListingStatus.ARCHIVED, "The lister closed their account"
    db.execute(delete(SavedListing).where(SavedListing.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.execute(update(Message).where(Message.sender_id == user.id).values(body=CLOSED_MESSAGE, warning=""))
    db.execute(update(IdentityCheck).where(IdentityCheck.user_id == user.id).values(name_on_card=""))
    for payee in db.scalars(select(Payee).where(Payee.user_id == user.id)):
        payee.account_number, payee.account_name = "0" * 6 + payee.account_number[-4:], ""
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=now))
    reference = f"closed-{user.id}"
    user.username, user.display_name = reference, "Closed account"
    user.phone, user.email, user.password_hash = None, None, ""
    user.totp_secret, user.totp_enabled_at, user.whatsapp_opt_in = None, None, False
    user.is_active = False
    db.flush()
    record(db, None, "account.closed", user, reference=reference)
