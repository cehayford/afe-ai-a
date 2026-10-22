"""The verification fee (plan Sprint 4, decision B6): a landlord pays per home before an
Afe verifier is sent. Reviewers can waive it, e.g. for the first 50 founding landlords."""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import NotAllowed, RuleViolation
from app.core.ghana import format_ghs
from app.db import utcnow
from app.modules.audit.log import record
from app.modules.notifications.service import notify
from app.modules.units.models import Unit

from .models import Payment, PaymentPurpose, PaymentStatus
from .providers import PaymentError, WebhookEvent, get_provider


def fee_pesewas(db: Session) -> int:
    """The verification fee now: nothing during the launch offer, then decision B6."""
    from app.modules.compliance.service import charges_free

    return 0 if charges_free(db) else get_settings().verification_fee_pesewas


def settled_fee(db: Session, unit: Unit) -> Payment | None:
    return db.scalar(
        select(Payment).where(
            Payment.unit_id == unit.id,
            Payment.purpose == PaymentPurpose.VERIFICATION_FEE,
            Payment.status.in_([PaymentStatus.PAID, PaymentStatus.WAIVED]),
        )
    )


def fee_settled(db: Session, unit: Unit) -> bool:
    return fee_pesewas(db) == 0 or settled_fee(db, unit) is not None


def start_verification_fee(db: Session, user, unit: Unit) -> Payment:
    if unit.registered_by_id != user.id:
        raise NotAllowed("Only the person who registered this home can pay its fee.")
    if fee_settled(db, unit):
        raise RuleViolation("The verification fee for this home is already settled.")
    provider = get_provider()
    reference = f"AFE-VF-{unit.id}-{secrets.token_hex(4).upper()}"
    return_url = f"{get_settings().frontend_url}/landlord/homes/{unit.id}?payment={reference}"
    try:
        checkout = provider.create_checkout(reference, fee_pesewas(db), user.email or "", user.phone or "", return_url)
    except PaymentError as exc:
        raise RuleViolation(f"Payment could not start: {exc}. Try again shortly.") from exc
    payment = Payment(
        reference=reference,
        user_id=user.id,
        unit_id=unit.id,
        purpose=PaymentPurpose.VERIFICATION_FEE,
        amount_pesewas=fee_pesewas(db),
        provider=provider.name,
        checkout_url=checkout.url,
        provider_data=checkout.provider_data,
    )
    db.add(payment)
    db.flush()
    record(db, user, "payment.started", payment, amount=payment.amount_pesewas)
    return payment


def apply_webhook(db: Session, event: WebhookEvent) -> Payment | None:
    """Idempotent: partners resend webhooks, and each resend must be harmless."""
    payment = db.scalar(select(Payment).where(Payment.reference == event.reference).with_for_update())
    if payment is None or payment.status != PaymentStatus.PENDING:
        return payment
    if not event.paid:
        payment.status = PaymentStatus.FAILED
    elif event.amount_pesewas != payment.amount_pesewas or event.currency != payment.currency:
        payment.status = PaymentStatus.FAILED
        payment.note = f"Amount mismatch: got {event.amount_pesewas} {event.currency}"
    else:
        payment.status = PaymentStatus.PAID
        payment.paid_at = utcnow()
    db.flush()
    record(db, None, "payment.webhook", payment, status=payment.status)
    if payment.status == PaymentStatus.PAID:
        if payment.purpose == PaymentPurpose.FEATURED_LISTING:
            _feature(db, payment)
        elif payment.purpose == PaymentPurpose.SUBSCRIPTION:
            from datetime import timedelta

            from app.modules.rentals.service import activate

            activate(db, payment.user, payment.note.removeprefix("plan:"), utcnow().date() + timedelta(days=30))
        else:
            notify(db, payment.user, "fee_paid", link=f"/landlord/homes/{payment.unit_id}",
                   amount=format_ghs(payment.amount_pesewas), unit=str(payment.unit), reference=payment.reference)
    return payment


def waive_fee(db: Session, unit: Unit, reviewer, note: str) -> Payment:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can waive fees.")
    if len(note.strip()) < 3:
        raise RuleViolation("Say why the fee is waived, e.g. founding landlord.")
    if settled_fee(db, unit):
        raise RuleViolation("The fee for this home is already settled.")
    payment = Payment(
        reference=f"AFE-WV-{unit.id}-{secrets.token_hex(4).upper()}",
        user_id=unit.registered_by_id,
        unit_id=unit.id,
        purpose=PaymentPurpose.VERIFICATION_FEE,
        amount_pesewas=0,
        provider="waiver",
        status=PaymentStatus.WAIVED,
        waived_by_id=reviewer.id,
        note=note.strip()[:300],
        paid_at=utcnow(),
    )
    db.add(payment)
    db.flush()
    record(db, reviewer, "payment.waived", payment, note=note)
    return payment


def payments_for(db: Session, user) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())))


# --- Featured listings (paid visibility, verified listings only) ------------------------------------


def start_featured(db: Session, user, listing) -> Payment:
    from app.modules.compliance.service import rule
    from app.modules.listings.models import ListingStatus

    if listing.lister_id != user.id:
        raise NotAllowed("Only the lister can feature this listing.")
    if listing.status != ListingStatus.LIVE:
        raise RuleViolation("Only live, verified listings can be featured.")
    from app.modules.compliance.service import charges_free, free_until

    if charges_free(db):
        # Launch offer: featuring is free, one period at a time so every lister gets a turn.
        if featured_until(db, listing.id):
            raise RuleViolation("During the launch offer a listing can be featured one period at a time.")
        payment = Payment(reference=f"AFE-FL-{listing.id}-{secrets.token_hex(4).upper()}", user_id=user.id,
                          listing_id=listing.id, purpose=PaymentPurpose.FEATURED_LISTING, amount_pesewas=0,
                          status=PaymentStatus.WAIVED, provider="launch_offer",
                          note=f"Free during the launch offer (until {free_until(db):%d %b %Y})", paid_at=utcnow())
        db.add(payment)
        db.flush()
        record(db, user, "payment.waived", payment, reason="launch_offer")
        _feature(db, payment)
        return payment
    amount = rule(db, "featured_fee_pesewas")
    provider = get_provider()
    reference = f"AFE-FL-{listing.id}-{secrets.token_hex(4).upper()}"
    return_url = f"{get_settings().frontend_url}/landlord/listings/{listing.id}?payment={reference}"
    try:
        checkout = provider.create_checkout(reference, amount, user.email or "", user.phone or "", return_url)
    except PaymentError as exc:
        raise RuleViolation(f"Payment could not start: {exc}. Try again shortly.") from exc
    payment = Payment(reference=reference, user_id=user.id, listing_id=listing.id, purpose=PaymentPurpose.FEATURED_LISTING,
                      amount_pesewas=amount, provider=provider.name, checkout_url=checkout.url,
                      provider_data=checkout.provider_data)
    db.add(payment)
    db.flush()
    record(db, user, "payment.started", payment, amount=amount)
    return payment


def _feature(db: Session, payment: Payment) -> None:
    """Start the featured period, or extend the current one."""
    from datetime import timedelta

    from app.modules.compliance.service import rule
    from app.modules.listings.models import FeaturedPlacement, Listing

    now = utcnow()
    current_end = db.scalar(
        select(FeaturedPlacement.ends_at)
        .where(FeaturedPlacement.listing_id == payment.listing_id, FeaturedPlacement.ends_at > now)
        .order_by(FeaturedPlacement.ends_at.desc())
    )
    starts = current_end or now
    placement = FeaturedPlacement(listing_id=payment.listing_id, payment_id=payment.id, starts_at=starts,
                                  ends_at=starts + timedelta(days=rule(db, "featured_days")))
    db.add(placement)
    db.flush()
    listing = db.get(Listing, payment.listing_id)
    notify(db, payment.user, "featured_paid", link=f"/landlord/listings/{listing.id}", listing=listing.title,
           until=placement.ends_at.strftime("%d %b"), reference=payment.reference)


def featured_until(db: Session, listing_id: int):
    from app.modules.listings.models import FeaturedPlacement

    return db.scalar(
        select(FeaturedPlacement.ends_at)
        .where(FeaturedPlacement.listing_id == listing_id, FeaturedPlacement.ends_at > utcnow())
        .order_by(FeaturedPlacement.ends_at.desc())
    )


def start_subscription_payment(db: Session, user, plan: str, amount: int) -> Payment:
    """A month of a landlord tools plan, through the hosted checkout."""
    provider = get_provider()
    reference = f"AFE-SUB-{user.id}-{secrets.token_hex(4).upper()}"
    return_url = f"{get_settings().frontend_url}/landlord/rentals?payment={reference}"
    try:
        checkout = provider.create_checkout(reference, amount, user.email or "", user.phone or "", return_url)
    except PaymentError as exc:
        raise RuleViolation(f"Payment could not start: {exc}. Try again shortly.") from exc
    payment = Payment(reference=reference, user_id=user.id, purpose=PaymentPurpose.SUBSCRIPTION, amount_pesewas=amount,
                      provider=provider.name, checkout_url=checkout.url, provider_data=checkout.provider_data,
                      note=f"plan:{plan}")
    db.add(payment)
    db.flush()
    record(db, user, "payment.started", payment, amount=amount, plan=plan)
    return payment
