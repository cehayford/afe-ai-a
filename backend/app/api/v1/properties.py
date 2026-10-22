"""Areas, homes, listings, search, and what renters do with a listing (save, enquire, book a
viewing). Public reads need no sign-in."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.config import get_settings
from app.core.envelope import Envelope, ok
from app.core.errors import NotAllowed, NotFound
from app.deps import DB, ApiUser, Lister, MaybeUser
from app.modules.areas.models import ServiceArea
from app.modules.billing.service import featured_until, start_featured
from app.modules.enquiries import service as enquiries
from app.modules.enquiries.models import SavedListing
from app.modules.listings import service as listings
from app.modules.listings.models import Listing
from app.modules.reviews.service import rating_summary, reviews_for_landlord
from app.modules.risk.flags import open_flags
from app.modules.units import service as units
from app.modules.units.models import Unit

from .. import schemas as s
from .common import get_or_404
from .messages import thread_out, viewing_out
from .progress import unit_progress

router = APIRouter(prefix="/properties", tags=["properties"])


def _cover(db, listing):
    return next(iter(listings.listing_photos(db, listing)), None)


@router.get("/areas", response_model=Envelope[list[s.AreaOut]])
def areas(db: DB):
    rows = db.scalars(select(ServiceArea).where(ServiceArea.is_active).order_by(ServiceArea.name))
    return ok([s.AreaOut.model_validate(a) for a in rows])


@router.get("/rent-index", response_model=Envelope[dict])
def rent_index(db: DB):
    """Accra verified rent index: median rent by area and size, from verified homes (last 90 days)."""
    from app.modules.insights.service import rent_index as compute

    return ok(compute(db))


@router.get("/areas/{slug}", response_model=Envelope[s.AreaOverviewOut])
def area_overview(db: DB, slug: str):
    """A neighbourhood page: verified rent ranges and the homes live there now."""
    area = db.scalar(select(ServiceArea).where(ServiceArea.slug == slug, ServiceArea.is_active))
    if area is None:
        raise NotFound("Afe isn't open in that area yet.")
    overview = listings.area_overview(db, area)
    live = listings.search_live(db, area.slug, limit=12)
    featured = listings.featured_ids(db, [li.id for li in live])
    return ok(s.AreaOverviewOut(
        area=s.AreaOut.model_validate(area), live=overview["live"],
        ranges=[s.RentRangeOut(**r) for r in overview["ranges"]],
        listings=[s.ListingOut.of(li, _cover(db, li), featured=li.id in featured) for li in live],
    ))


@router.get("/search", response_model=Envelope[list[s.ListingOut]])
def search(
    db: DB,
    area: str | None = None,
    bedrooms: Annotated[int | None, Query(ge=0)] = None,
    max_rent_ghs: Annotated[Decimal | None, Query(gt=0)] = None,
):
    rows = listings.search_live(db, area, bedrooms, int(max_rent_ghs * 100) if max_rent_ghs else None)
    featured = listings.featured_ids(db, [li.id for li in rows])
    return ok([s.ListingOut.of(li, _cover(db, li), featured=li.id in featured) for li in rows], count=len(rows))


# --- Homes (landlords and agents) ------------------------------------------------------------------


@router.post("/units", response_model=Envelope[s.MyUnitOut], status_code=201)
def register_unit(db: DB, user: Lister, body: s.UnitIn):
    area = db.scalar(select(ServiceArea).where(ServiceArea.slug == body.area_slug))
    if area is None:
        raise NotFound("Unknown area.")
    unit = units.register_unit(
        db,
        user,
        area,
        body.digital_address,
        body.unit_label,
        body.lat,
        body.lng,
        body.property_type,
        body.bedrooms,
        body.bathrooms,
        body.landmark,
    )
    return ok(unit_progress(db, unit))


@router.get("/units/{unit_id}", response_model=Envelope[s.MyUnitOut])
def get_unit(db: DB, user: ApiUser, unit_id: int):
    unit = get_or_404(db, Unit, unit_id, "Home")
    if unit.registered_by_id != user.id and not user.is_staff:
        raise NotFound("Home not found.")
    return ok(unit_progress(db, unit))


# --- Listings (landlords and agents) ------------------------------------------------------------------


def _own_listing(db, user, listing_id) -> Listing:
    listing = get_or_404(db, Listing, listing_id, "Listing")
    if listing.lister_id != user.id:
        raise NotFound("Listing not found.")
    return listing


@router.post("/listings", response_model=Envelope[s.ListingOut], status_code=201)
def create_listing(db: DB, user: Lister, body: s.ListingIn):
    unit = get_or_404(db, Unit, body.unit_id, "Home")
    if unit.registered_by_id != user.id and not units.has_authority(db, user, unit):
        raise NotAllowed("You can only list homes you registered or are authorised to let.")
    listing = listings.create_draft(
        db,
        user,
        unit,
        body.title,
        body.description,
        int(body.rent_ghs * 100),
        body.advance_months,
        body.min_lease_months,
        body.available_from,
    )
    return ok(s.ListingOut.of(listing, _cover(db, listing)))


@router.get("/listings/{listing_id}", response_model=Envelope[s.ListingDetailOut])
def my_listing(db: DB, user: Lister, listing_id: int):
    listing = _own_listing(db, user, listing_id)
    return ok(
        _detail(db, listing, user),
        blockers=listings.publish_blockers(db, listing),
        flags=[f.explanation for f in open_flags(db, listing)],
    )


@router.patch("/listings/{listing_id}", response_model=Envelope[s.ListingOut])
def edit_listing(db: DB, user: Lister, listing_id: int, body: s.ListingUpdateIn):
    listing = _own_listing(db, user, listing_id)
    changes = body.model_dump(exclude_none=True)
    if "rent_ghs" in changes:
        changes["rent_pesewas"] = int(changes.pop("rent_ghs") * 100)
    return ok(s.ListingOut.of(listings.update_listing(db, listing, user, **changes), _cover(db, listing)))


@router.post("/listings/{listing_id}/submit", response_model=Envelope[s.ListingOut])
def submit_listing(db: DB, user: Lister, listing_id: int):
    listing = listings.submit_for_review(db, _own_listing(db, user, listing_id), user)
    return ok(
        s.ListingOut.of(listing, _cover(db, listing)),
        flags=[f.explanation for f in open_flags(db, listing)],
        blockers=listings.publish_blockers(db, listing),
    )


@router.post("/listings/{listing_id}/feature", response_model=Envelope[s.PaymentOut], status_code=201)
def feature_listing(db: DB, user: Lister, listing_id: int):
    """Paid visibility: returns a payment whose checkout_url the lister is sent to."""
    return ok(s.PaymentOut.of(start_featured(db, user, _own_listing(db, user, listing_id))))


@router.post("/listings/{listing_id}/archive", response_model=Envelope[s.ListingOut])
def archive_listing(db: DB, user: Lister, listing_id: int):
    listing = listings.archive_listing(db, _own_listing(db, user, listing_id), user)
    return ok(s.ListingOut.of(listing, _cover(db, listing)))


# --- Public listing and what renters do with it --------------------------------------------------------


def _detail(db, listing, user=None) -> s.ListingDetailOut:
    saved = bool(
        user
        and db.scalar(
            select(SavedListing.id).where(SavedListing.user_id == user.id, SavedListing.listing_id == listing.id)
        )
    )
    photos = listings.listing_photos(db, listing)
    rating, count = rating_summary(db, listing.lister_id)
    until = featured_until(db, listing.id)
    return s.ListingDetailOut.of(
        listing,
        next(iter(photos), None),
        description=listing.description,
        lister_name=listing.lister.name,
        lister_role=listing.lister.role_label,
        city=listing.unit.area.city,
        photos=[s.PhotoOut.of(p) for p in photos],
        verification=[
            s.PanelLineOut(text=line.text, date=line.date) for line in listings.verification_panel(db, listing)
        ],
        saved=saved,
        landlord_rating=rating,
        landlord_review_count=count,
        reviews=[s.ReviewOut(id=r.id, rating=r.rating, body=r.body, author_name=r.author.name.split(" ")[0],
                             created_at=r.created_at) for r in reviews_for_landlord(db, listing.lister_id, 5)],
        featured_until=until,
        featured=until is not None,
        tenancy_available=get_settings().protected_payments_enabled,
    )


def _live(db, reference: str) -> Listing:
    listing = listings.get_live(db, reference.upper())
    if listing is None:
        raise NotFound("No live listing with that reference.")
    return listing


@router.get("/{reference}", response_model=Envelope[s.ListingDetailOut])
def listing_detail(db: DB, user: MaybeUser, reference: str):
    return ok(_detail(db, _live(db, reference), user))


@router.post("/{reference}/save", response_model=Envelope[dict])
def save(db: DB, user: ApiUser, reference: str):
    enquiries.save_listing(db, user, _live(db, reference))
    return ok({"saved": True})


@router.delete("/{reference}/save", response_model=Envelope[dict])
def unsave(db: DB, user: ApiUser, reference: str):
    listing = db.scalar(select(Listing).where(Listing.reference == reference.upper()))
    if listing:
        enquiries.unsave_listing(db, user, listing)
    return ok({"saved": False})


@router.post("/{reference}/enquiries", response_model=Envelope[s.ThreadOut], status_code=201)
def enquire(db: DB, user: ApiUser, reference: str, body: s.EnquiryIn):
    thread = enquiries.start_enquiry(db, user, _live(db, reference), body.body)
    return ok(thread_out(thread, user))


@router.post("/{reference}/viewings", response_model=Envelope[s.ViewingOut], status_code=201)
def request_viewing(db: DB, user: ApiUser, reference: str, body: s.ViewingIn):
    viewing = enquiries.request_viewing(db, user, _live(db, reference), body.when, body.note)
    return ok(viewing_out(viewing, user))
