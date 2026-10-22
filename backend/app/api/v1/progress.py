"""Where a landlord's home is in the verification journey, for their dashboard."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.modules.billing.service import fee_pesewas, fee_settled
from app.modules.listings.models import Listing, ListingStatus
from app.modules.listings.service import listing_photos
from app.modules.units.models import AuthorityStatus, Unit
from app.modules.verification import service as verification
from app.modules.verification.models import VerificationStatus, VisitOutcome

from .. import schemas as s


def unit_progress(db: Session, unit: Unit) -> s.MyUnitOut:
    authorities = [a for a in unit.authority_records if a.status != AuthorityStatus.REJECTED]
    settled = fee_settled(db, unit)
    current = verification.current_verification(db, unit=unit)
    history = verification.decision_history(db, unit=unit, limit=1)
    latest_decision = history[0] if history else None
    visit = verification.latest_completed_visit(db, unit)
    assignment = verification.open_assignment(db, unit)
    recent_pass = (
        visit is not None
        and visit.outcome == VisitOutcome.PASSED
        and utcnow() - visit.completed_at <= get_settings().field_visit_max_age
    )

    if current:
        stage = "verified"
    elif not authorities:
        stage = "documents"
    elif not settled:
        stage = "fee"
    elif recent_pass and (latest_decision is None or latest_decision.decided_at < visit.completed_at):
        stage = "review"
    elif latest_decision and latest_decision.status == VerificationStatus.REJECTED and not assignment:
        stage = "rejected"
    else:
        stage = "visit"

    listings = db.scalars(
        select(Listing)
        .where(Listing.unit_id == unit.id, Listing.status != ListingStatus.ARCHIVED)
        .order_by(Listing.id.desc())
    )
    return s.MyUnitOut(
        unit=s.UnitOut.model_validate(unit),
        stage=stage,
        authorities=[s.AuthorityOut.model_validate(a) for a in unit.authority_records],
        fee_required=fee_pesewas(db) > 0,
        fee_settled=settled,
        visit_scheduled_for=assignment.scheduled_for if assignment else None,
        latest_visit_outcome=visit.outcome if visit else None,
        verification=s.VerificationOut.of(latest_decision) if latest_decision else None,
        listings=[s.ListingOut.of(li, next(iter(listing_photos(db, li)), None)) for li in listings],
    )
