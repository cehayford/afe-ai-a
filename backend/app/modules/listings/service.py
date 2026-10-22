from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.db import utcnow
from app.modules.areas.models import ServiceArea
from app.modules.audit.log import record
from app.modules.detection.hooks import enqueue, enqueue_text, label
from app.modules.notifications.service import notify
from app.modules.risk.flags import open_flags
from app.modules.risk.models import Severity
from app.modules.risk.rules import evaluate_listing
from app.modules.units.models import Unit
from app.modules.units.service import accepted_authority, has_authority
from app.modules.verification.models import VisitOutcome, VisitPhoto
from app.modules.verification.service import current_verification

from .models import FeaturedPlacement, Listing, ListingStatus


def create_draft(
    db: Session,
    lister,
    unit: Unit,
    title: str,
    description: str,
    rent_pesewas: int,
    advance_months: int,
    min_lease_months: int,
    available_from: date,
) -> Listing:
    if not lister.is_lister:
        raise NotAllowed("Only landlords and agents can create listings.")
    if rent_pesewas <= 0:
        raise InvalidInput("Enter the monthly rent.")
    listing = Listing(
        unit_id=unit.id,
        lister_id=lister.id,
        title=title.strip(),
        description=description.strip(),
        rent_pesewas=rent_pesewas,
        advance_months=advance_months,
        min_lease_months=min_lease_months,
        available_from=available_from,
    )
    db.add(listing)
    db.flush()
    record(db, lister, "listing.created", listing)
    return listing


def submit_for_review(db: Session, listing: Listing, actor) -> Listing:
    if listing.lister_id != actor.id:
        raise NotAllowed("Only the lister can submit this listing.")
    if listing.status not in (ListingStatus.DRAFT, ListingStatus.PAUSED):
        raise RuleViolation(f"A listing that is {listing.status.replace('_', ' ')} cannot be submitted.")
    listing.status = ListingStatus.PENDING_REVIEW
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise RuleViolation("This home already has an active listing.") from exc
    evaluate_listing(db, listing)
    enqueue_text(db, listing)
    enqueue(db, "price", listing)
    record(db, actor, "listing.submitted", listing)
    return listing


def publish_blockers(db: Session, listing: Listing) -> list[str]:
    """Everything that stops a listing going live, in plain words. Empty means it can go live."""
    reasons = []
    unit, lister = listing.unit, listing.lister
    if not unit.area.is_active:
        reasons.append(f"Afe is not open in {unit.area.name} yet.")
    if current_verification(db, party=lister) is None:
        reasons.append("The landlord or agent is not currently verified.")
    if current_verification(db, unit=unit) is None:
        reasons.append("The home has not been verified by an Afe visit.")
    if not has_authority(db, lister, unit):
        reasons.append("The lister has no accepted authority to let this home.")
    for subject in (listing, unit, lister):
        for flag in open_flags(db, subject, min_severity=Severity.HIGH):
            reasons.append(f"Open risk flag: {flag.explanation}")
    return reasons


def publish(db: Session, listing: Listing, reviewer) -> Listing:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can publish listings.")
    if listing.status != ListingStatus.PENDING_REVIEW:
        raise RuleViolation("Only listings waiting for review can be published.")
    reasons = publish_blockers(db, listing)
    if reasons:
        raise RuleViolation("This listing cannot go live yet.", reasons=reasons)
    listing.status = ListingStatus.LIVE
    listing.published_at = utcnow()
    listing.status_reason = ""
    db.flush()
    record(db, reviewer, "listing.published", listing)
    # Publishing means a reviewer read the listing and its flags: a "genuine" label.
    label(db, listing, fraud=False, source="publish", decided_by=reviewer)
    notify(
        db,
        listing.lister,
        "listing_live",
        link=f"/homes/{listing.reference}",
        listing=listing.title,
        reference=listing.reference,
    )
    return listing


def pause_listings_for(db: Session, *, party=None, unit=None, actor=None, reason: str) -> int:
    q = select(Listing).where(Listing.status == ListingStatus.LIVE)
    q = q.where(Listing.lister_id == party.id) if party is not None else q.where(Listing.unit_id == unit.id)
    listings = list(db.scalars(q.with_for_update()))
    for listing in listings:
        listing.status = ListingStatus.PAUSED
        listing.status_reason = reason
        db.flush()
        record(db, actor, "listing.paused", listing, reason=reason)
    return len(listings)


def search_live(
    db: Session,
    area_slug: str | None = None,
    bedrooms: int | None = None,
    max_rent_pesewas: int | None = None,
    limit: int = 60,
) -> list[Listing]:
    q = (
        select(Listing)
        .join(Listing.unit)
        .join(Unit.area)
        .where(Listing.status == ListingStatus.LIVE)
        .options(joinedload(Listing.unit).joinedload(Unit.area), joinedload(Listing.lister))
        .order_by(_featured_now().desc(), Listing.published_at.desc())
        .limit(limit)
    )
    if area_slug:
        q = q.where(ServiceArea.slug == area_slug)
    if bedrooms is not None:
        q = q.where(Unit.bedrooms >= 3) if bedrooms >= 3 else q.where(Unit.bedrooms == bedrooms)
    if max_rent_pesewas:
        q = q.where(Listing.rent_pesewas <= max_rent_pesewas)
    return list(db.scalars(q).unique())


def _featured_now():
    """True when the listing has a paid featured period running now."""
    return (
        select(FeaturedPlacement.id)
        .where(FeaturedPlacement.listing_id == Listing.id, FeaturedPlacement.ends_at > utcnow(),
               FeaturedPlacement.starts_at <= utcnow())
        .exists()
    )


def get_live(db: Session, reference: str) -> Listing | None:
    return db.scalar(select(Listing).where(Listing.reference == reference, Listing.status == ListingStatus.LIVE))


def listing_photos(db: Session, listing: Listing) -> list[VisitPhoto]:
    """A verified listing shows only the photos Afe took on the visit that verified the home."""
    verification = current_verification(db, unit=listing.unit)
    if verification is None or verification.field_visit_id is None:
        return []
    return list(
        db.scalars(
            select(VisitPhoto)
            .where(VisitPhoto.visit_id == verification.field_visit_id, VisitPhoto.duplicate_of_id.is_(None))
            .order_by(VisitPhoto.taken_at, VisitPhoto.id)
        )
    )


@dataclass(frozen=True)
class PanelLine:
    text: str
    date: datetime


def verification_panel(db: Session, listing: Listing) -> list[PanelLine]:
    """What the renter sees: each check in plain words, with its date (plan §5)."""
    lines: list[PanelLine] = []
    party_v = current_verification(db, party=listing.lister)
    unit_v = current_verification(db, unit=listing.unit)
    if party_v and party_v.identity_check:
        role = "Landlord" if listing.lister.role == "landlord" else "Agent"
        lines.append(PanelLine(f"{role}'s Ghana Card checked", party_v.identity_check.created_at))
    authority = accepted_authority(db, listing.lister, listing.unit)
    if authority:
        lines.append(PanelLine(f"{authority.document_label} sighted", authority.reviewed_at))
        if authority.owner_confirmed_at:
            lines.append(PanelLine("Owner confirmed by phone", authority.owner_confirmed_at))
    if unit_v and unit_v.field_visit and unit_v.field_visit.outcome == VisitOutcome.PASSED:
        lines.append(PanelLine("Visited by Afe", unit_v.field_visit.completed_at))
        lines.append(PanelLine("Photos taken by Afe", unit_v.field_visit.completed_at))
    return lines


EDITABLE = {"title", "description", "rent_pesewas", "advance_months", "min_lease_months", "available_from"}


def update_listing(db: Session, listing: Listing, lister, **changes) -> Listing:
    """Edit a draft or paused listing. Live listings go back to review after any edit, so
    a verified listing can't be changed into something else unseen."""
    if listing.lister_id != lister.id:
        raise NotAllowed("Only the lister can edit this listing.")
    if listing.status in (ListingStatus.LET, ListingStatus.ARCHIVED):
        raise RuleViolation("This listing is closed. Create a new one instead.")
    changed = {k: v for k, v in changes.items() if k in EDITABLE and v is not None and getattr(listing, k) != v}
    if not changed:
        return listing
    if changed.get("rent_pesewas", 1) <= 0:
        raise InvalidInput("Enter the monthly rent.")
    for key, value in changed.items():
        setattr(listing, key, value.strip() if isinstance(value, str) else value)
    if listing.status == ListingStatus.LIVE:
        listing.status = ListingStatus.PENDING_REVIEW
        listing.status_reason = "Edited; waiting for review again"
        evaluate_listing(db, listing)
    db.flush()
    record(db, lister, "listing.edited", listing, fields=sorted(changed))
    return listing


def archive_listing(db: Session, listing: Listing, lister) -> Listing:
    if listing.lister_id != lister.id:
        raise NotAllowed("Only the lister can archive this listing.")
    listing.status = ListingStatus.ARCHIVED
    listing.status_reason = "Archived by the lister"
    db.flush()
    record(db, lister, "listing.archived", listing)
    return listing


def featured_ids(db: Session, listing_ids: list[int]) -> set[int]:
    if not listing_ids:
        return set()
    now = utcnow()
    return set(db.scalars(
        select(FeaturedPlacement.listing_id).where(
            FeaturedPlacement.listing_id.in_(listing_ids), FeaturedPlacement.starts_at <= now,
            FeaturedPlacement.ends_at > now)
    ))


MIN_FOR_OWN_RANGE = 3


def area_overview(db: Session, area) -> dict:
    """Rent ranges by size for one neighbourhood: from Afe's own verified listings where there
    are at least 3 of a size, otherwise from the manual price survey. Says which it used."""
    import statistics

    from app.modules.areas.models import PriceBand

    rows = db.execute(
        select(Unit.bedrooms, Listing.rent_pesewas).join(Listing.unit)
        .where(Unit.area_id == area.id, Listing.status.in_([ListingStatus.LIVE, ListingStatus.LET]))
    ).all()
    by_size: dict[int, list[int]] = {}
    for beds, rent in rows:
        by_size.setdefault(min(beds, 3), []).append(rent)
    bands = {b.bedrooms: b for b in db.scalars(
        select(PriceBand).where(PriceBand.area_id == area.id).order_by(PriceBand.as_of)
    )}
    ranges = []
    for size in (0, 1, 2, 3):
        rents = sorted(by_size.get(size, []))
        if len(rents) >= MIN_FOR_OWN_RANGE:
            ranges.append({"bedrooms": size, "low": rents[0], "median": int(statistics.median(rents)),
                           "high": rents[-1], "count": len(rents), "source": "afe"})
        elif size in bands:
            b = bands[size]
            ranges.append({"bedrooms": size, "low": b.low_pesewas, "median": b.median_pesewas, "high": b.high_pesewas,
                           "count": len(rents), "source": "survey"})
    return {"ranges": ranges, "live": len(search_live(db, area.slug, limit=500))}
