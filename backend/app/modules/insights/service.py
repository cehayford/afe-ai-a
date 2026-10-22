"""Insights (roadmap workstream E): know every week whether the build plan's targets (§13)
are being hit, what a verification really costs, how many deals skip protection, and a
public rent index from verified homes."""

import statistics
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, RuleViolation
from app.db import utcnow
from app.modules.alerts.models import SavedSearch
from app.modules.areas.models import ServiceArea
from app.modules.audit.log import record
from app.modules.compliance.service import rule
from app.modules.detection.models import DetectionLabel
from app.modules.enquiries.models import Thread, Viewing, ViewingOutcome, ViewingStatus
from app.modules.listings.models import Listing, ListingStatus
from app.modules.units.models import Unit
from app.modules.verification.models import FieldVisit, VisitOutcome

OUTCOMES = {
    "rented_through_afe": "Yes, and I paid through Afe",
    "paid_directly": "Yes, but I paid the landlord directly",
    "not_renting": "No, I'm not renting it",
    "still_deciding": "I'm still deciding",
}


# --- Leakage: deals that skip protection --------------------------------------------------------------


def record_outcome(db: Session, renter, viewing: Viewing, answer: str) -> ViewingOutcome:
    """The renter's answer after a viewing. Honest answers need no judgement: nobody is
    penalised for paying directly; we only count how often it happens."""
    if viewing.renter_id != renter.id:
        raise NotFound("Viewing not found.")
    if viewing.status != ViewingStatus.COMPLETED:
        raise RuleViolation("You can answer after the viewing has happened.")
    if answer not in OUTCOMES:
        raise RuleViolation("Choose one of the answers.")
    row = db.scalar(select(ViewingOutcome).where(ViewingOutcome.viewing_id == viewing.id))
    if row is None:
        row = ViewingOutcome(viewing_id=viewing.id, answer=answer)
        db.add(row)
    else:
        row.answer, row.updated_at = answer, utcnow()
    db.flush()
    record(db, renter, "viewing.outcome", viewing, answer=answer)
    return row


def leakage(db: Session, days: int = 90) -> dict:
    since = utcnow() - timedelta(days=days)
    counts = dict(db.execute(
        select(ViewingOutcome.answer, func.count()).where(ViewingOutcome.created_at > since).group_by(ViewingOutcome.answer)
    ).all())
    rented = counts.get("rented_through_afe", 0) + counts.get("paid_directly", 0)
    return {
        "answers": {k: counts.get(k, 0) for k in OUTCOMES},
        "rate": round(counts.get("paid_directly", 0) / rented, 2) if rented else None,
    }


# --- Cost per verification ---------------------------------------------------------------------------------


def verification_cost(db: Session, days: int = 30) -> dict:
    """Verifier time (visit plus travel) at the hourly cost rule, plus fares, per completed
    visit, against the verification fee the plan wants it to fit inside (decision B6)."""
    from app.config import get_settings

    since = utcnow() - timedelta(days=days)
    visits = db.scalars(select(FieldVisit).where(
        FieldVisit.outcome != VisitOutcome.IN_PROGRESS, FieldVisit.completed_at > since,
        FieldVisit.travel_minutes.is_not(None),
    )).all()
    hourly = rule(db, "verifier_hour_cost_pesewas")
    costs = []
    for v in visits:
        minutes = (v.completed_at - v.started_at).total_seconds() / 60 + (v.travel_minutes or 0)
        costs.append(round(minutes / 60 * hourly) + (v.transport_pesewas or 0))
    fee = get_settings().verification_fee_pesewas
    return {
        "visits_measured": len(costs),
        "median_pesewas": int(statistics.median(costs)) if costs else None,
        "fee_pesewas": fee,
        "within_fee": (statistics.median(costs) <= fee) if costs and fee else None,
    }


# --- Targets --------------------------------------------------------------------------------------------------


def _median_days_to_live(db: Session, days: int = 30) -> tuple[float | None, int]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(Unit.created_at, func.min(Listing.published_at)).join(Listing, Listing.unit_id == Unit.id)
        .where(Listing.published_at.is_not(None)).group_by(Unit.id)
    ).all()
    spans = [(live - made).total_seconds() / 86400 for made, live in rows if live and live > since]
    return (round(statistics.median(spans), 1) if spans else None), len(spans)


def targets(db: Session) -> list[dict]:
    """The build plan's §13 targets, each with its value now and whether it's met."""
    from app.modules.ops.service import verifier_totals
    from app.modules.tenancies.service import held_total

    live = db.scalar(select(func.count()).select_from(Listing).where(Listing.status == ListingStatus.LIVE))
    fraud = db.scalar(select(func.count()).select_from(DetectionLabel).where(
        DetectionLabel.subject_type.in_(["listings", "units"]), DetectionLabel.outcome == "fraud",
        DetectionLabel.source.in_(["report", "flag"]), DetectionLabel.disputed.is_(False)))
    median_days, homes = _median_days_to_live(db)
    reversal = verifier_totals(db)
    leak = leakage(db)
    cost = verification_cost(db)
    since = utcnow() - timedelta(days=30)
    threads = db.scalar(select(func.count()).select_from(Thread).where(Thread.created_at > since))
    booked = db.scalar(select(func.count(func.distinct(Viewing.thread_id))).where(Viewing.created_at > since))
    subscribers = db.scalar(select(func.count(func.distinct(SavedSearch.user_id))).where(SavedSearch.active.is_(True)))

    def row(name, value, target, met, note=""):
        return {"name": name, "value": value, "target": target, "met": met, "note": note}

    return [
        row("Verified listings live", live, "100 by W14, about 400 by W52", live >= 100),
        row("Confirmed fraud on verified listings", fraud, "0", fraud == 0, "Any case triggers a full review"),
        row("Median days from home registered to live", median_days, "7 or fewer",
            None if median_days is None else median_days <= 7, f"{homes} homes in the last 30 days"),
        row("Verifier reversals (failed re-checks)", reversal["reversals"], "0",
            reversal["reversals"] == 0, f"{reversal['rechecked']} re-checks so far"),
        row("Share of lets paid outside Afe", leak["rate"], "measured, then falling",
            None, f"{sum(leak['answers'].values())} answers in 90 days"),
        row("Median cost of a verification (pesewas)", cost["median_pesewas"], "within the verification fee",
            cost["within_fee"], f"{cost['visits_measured']} visits measured"),
        row("Enquiries that book a viewing", round(booked / threads, 2) if threads else None, "rising", None,
            f"{threads} enquiries in 30 days"),
        row("People with alerts on", subscribers, "1,000 by W30", subscribers >= 1000),
        row("Held in protected payments now (pesewas)", held_total(db), "within pilot limits", None),
    ]


# --- Accra verified rent index ------------------------------------------------------------------------------------


def rent_index(db: Session, days: int = 90) -> dict:
    """Median monthly rent by area and size, from verified homes listed in the last 90 days.
    A figure appears only when at least 3 homes back it."""
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(ServiceArea.name, ServiceArea.slug, Unit.bedrooms, Listing.rent_pesewas)
        .join(Unit, Unit.area_id == ServiceArea.id).join(Listing, Listing.unit_id == Unit.id)
        .where(Listing.status.in_([ListingStatus.LIVE, ListingStatus.LET]), Listing.published_at > since)
    ).all()
    cells: dict[tuple[str, str, int], list[int]] = {}
    for name, slug, beds, rent in rows:
        cells.setdefault((name, slug, min(beds, 3)), []).append(rent)
    areas: dict[str, dict] = {}
    for (name, slug, beds), rents in sorted(cells.items()):
        area = areas.setdefault(slug, {"name": name, "slug": slug, "sizes": {}})
        if len(rents) >= 3:
            area["sizes"][beds] = {"median": int(statistics.median(rents)), "count": len(rents)}
    return {"period_days": days, "as_of": utcnow().date().isoformat(),
            "areas": [a for a in areas.values() if a["sizes"]]}
