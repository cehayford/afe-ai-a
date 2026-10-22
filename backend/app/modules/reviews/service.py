from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, NotFound, RuleViolation
from app.modules.audit.log import record
from app.modules.notifications.service import notify
from app.modules.tenancies.models import Tenancy, TenancyStatus

from .models import Review


def write_review(db: Session, tenant, t: Tenancy, rating: int, body: str) -> Review:
    if t.tenant_id != tenant.id:
        raise NotFound("Tenancy not found.")
    if t.status != TenancyStatus.RELEASED:
        raise RuleViolation("You can review once you've moved in and the payment has been released.")
    if not 1 <= rating <= 5:
        raise InvalidInput("Give a rating from 1 to 5.")
    if len(body.strip()) < 20:
        raise InvalidInput("Write a few sentences other renters would find useful.")
    review = Review(tenancy_id=t.id, author_id=tenant.id, landlord_id=t.landlord_id, listing_id=t.listing_id,
                    rating=rating, body=body.strip()[:2000])
    try:
        with db.begin_nested():
            db.add(review)
            db.flush()
    except IntegrityError as exc:
        raise RuleViolation("You've already reviewed this tenancy.") from exc
    record(db, tenant, "review.written", review, rating=rating)
    notify(db, t.landlord, "review_received", link="/landlord", rating=rating)
    return review


def hide_review(db: Session, reviewer, review: Review, note: str) -> Review:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can hide reviews.")
    review.hidden = True
    db.flush()
    record(db, reviewer, "review.hidden", review, note=note)
    return review


def reviews_for_landlord(db: Session, landlord_id: int, limit: int = 20) -> list[Review]:
    return list(
        db.scalars(
            select(Review)
            .where(Review.landlord_id == landlord_id, Review.hidden.is_(False))
            .order_by(Review.created_at.desc())
            .limit(limit)
        )
    )


def reviews_about(db: Session, landlord_id: int, limit: int = 50) -> list[Review]:
    """Every review of a landlord, hidden ones too, newest first: what a reviewer moderates."""
    return list(
        db.scalars(select(Review).where(Review.landlord_id == landlord_id).order_by(Review.created_at.desc()).limit(limit))
    )


def rating_summary(db: Session, landlord_id: int) -> tuple[float | None, int]:
    avg, count = db.execute(
        select(func.avg(Review.rating), func.count()).where(Review.landlord_id == landlord_id, Review.hidden.is_(False))
    ).one()
    return (round(float(avg), 1) if avg is not None else None), count


def review_for_tenancy(db: Session, t: Tenancy) -> Review | None:
    return db.scalar(select(Review).where(Review.tenancy_id == t.id))
