"""Opening a new neighbourhood (roadmap workstream H, build plan §17). An area opens to
listings only when its boundary, its price survey and a verifier are all in place."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.modules.accounts.models import Role, User
from app.modules.audit.log import record

from .models import PriceBand, ServiceArea

MIN_SURVEYED_SIZES = 2


def _require_admin(actor: User) -> None:
    if actor.role != Role.ADMIN:
        raise NotAllowed("Only an Afe admin can open areas.")


def _check_boundary(boundary: list) -> list[list[float]]:
    try:
        points = [[float(lat), float(lng)] for lat, lng in boundary]
    except (TypeError, ValueError) as exc:
        raise InvalidInput("The boundary must be a list of [latitude, longitude] points.") from exc
    if len(points) < 3:
        raise InvalidInput("Draw the boundary with at least 3 points.")
    if not all(4.5 <= lat <= 11.5 and -3.5 <= lng <= 1.5 for lat, lng in points):
        raise InvalidInput("The boundary must be inside Ghana.")
    return points


def readiness(db: Session, area: ServiceArea) -> list[str]:
    """What's missing before the area can open. Empty means ready."""
    missing = []
    if len(area.boundary or []) < 3:
        missing.append("a boundary")
    sizes = db.scalar(select(func.count(func.distinct(PriceBand.bedrooms))).where(PriceBand.area_id == area.id))
    if sizes < MIN_SURVEYED_SIZES:
        missing.append(f"price survey for at least {MIN_SURVEYED_SIZES} home sizes")
    verifiers = db.scalar(select(func.count()).select_from(User).where(
        User.role == Role.FIELD_VERIFIER, User.is_active.is_(True)))
    if not verifiers:
        missing.append("an active field verifier")
    return missing


def create_area(db: Session, actor: User, name: str, slug: str, city: str, boundary: list) -> ServiceArea:
    _require_admin(actor)
    slug = slug.strip().lower()
    if not slug.replace("-", "").isalnum() or len(slug) < 3:
        raise InvalidInput("Use a short web name like east-legon.")
    area = ServiceArea(name=name.strip(), slug=slug, city=city.strip() or "Accra", is_active=False,
                       boundary=_check_boundary(boundary))
    try:
        with db.begin_nested():
            db.add(area)
            db.flush()
    except IntegrityError as exc:
        raise RuleViolation("That web name is taken.") from exc
    record(db, actor, "area.created", area)
    return area


def load_price_survey(db: Session, actor: User, area: ServiceArea, rows: list[dict]) -> int:
    """rows: {bedrooms, low_ghs, median_ghs, high_ghs}, from the manual survey (build plan §7)."""
    _require_admin(actor)
    today = date.today()
    count = 0
    for r in rows:
        beds, low, mid, high = int(r["bedrooms"]), int(r["low_ghs"]), int(r["median_ghs"]), int(r["high_ghs"])
        if not (0 <= beds <= 3 and 0 < low <= mid <= high):
            raise InvalidInput(f"Check the row for {beds} bedrooms: low, middle and high must rise.")
        db.add(PriceBand(area_id=area.id, bedrooms=beds, low_pesewas=low * 100, median_pesewas=mid * 100,
                         high_pesewas=high * 100, as_of=today))
        count += 1
    db.flush()
    record(db, actor, "area.price_survey_loaded", area, rows=count)
    return count


def set_open(db: Session, actor: User, area: ServiceArea, open_: bool) -> ServiceArea:
    _require_admin(actor)
    if open_:
        missing = readiness(db, area)
        if missing:
            raise RuleViolation(f"{area.name} isn't ready. Still needed: {', '.join(missing)}.")
    else:
        from app.modules.listings.models import Listing, ListingStatus
        from app.modules.units.models import Unit

        live = db.scalar(select(func.count()).select_from(Listing).join(Unit, Listing.unit_id == Unit.id)
                         .where(Unit.area_id == area.id, Listing.status == ListingStatus.LIVE))
        if live:
            raise RuleViolation(f"{area.name} has {live} live listings. Pause them before closing the area.")
    area.is_active = open_
    db.flush()
    record(db, actor, "area.opened" if open_ else "area.closed", area)
    return area
