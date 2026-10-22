"""The signed-in person: profile, devices, notifications, saved homes, payments, and a
landlord's homes and listings."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.envelope import Envelope, ok
from app.core.errors import NotFound
from app.deps import DB, ApiUser, Lister
from app.modules.accounts import privacy
from app.modules.accounts.service import active_devices, set_whatsapp_opt_in
from app.modules.alerts import service as alerts
from app.modules.areas.models import ServiceArea
from app.modules.billing.service import payments_for
from app.modules.enquiries.service import saved_listings
from app.modules.identity.service import latest_check
from app.modules.listings.models import Listing, ListingStatus
from app.modules.listings.service import listing_photos
from app.modules.notifications import service as notifications
from app.modules.ops import service as ops
from app.modules.tenancies import service as tenancies
from app.modules.units.models import Unit
from app.modules.verification import service as verification

from .. import schemas as s
from .progress import unit_progress

router = APIRouter(prefix="/me", tags=["me"])


def _verification_status(db, user) -> s.VerificationStatusOut | None:
    if not user.is_lister:
        return None
    current = verification.current_verification(db, party=user)
    history = verification.decision_history(db, party=user, limit=1)
    check = latest_check(db, user)
    return s.VerificationStatusOut(
        verified=current is not None,
        expires_at=current.expires_at if current else None,
        latest_decision=history[0].status if history else None,
        identity_check=check.status if check else None,
    )


@router.get("", response_model=Envelope[s.MeOut])
def me(db: DB, user: ApiUser):
    return ok(
        s.MeOut(
            user=s.UserOut.of(user),
            verification=_verification_status(db, user),
            unread_notifications=notifications.unread_count(db, user),
        )
    )


@router.patch("", response_model=Envelope[s.UserOut])
def update_profile(db: DB, user: ApiUser, body: s.ProfileIn):
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.email is not None:
        user.email = body.email.strip() or None
    if body.whatsapp_opt_in is not None:
        set_whatsapp_opt_in(db, user, body.whatsapp_opt_in, "settings")
    db.flush()
    return ok(s.UserOut.of(user))


@router.get("/devices", response_model=Envelope[list[s.DeviceOut]])
def devices(db: DB, user: ApiUser):
    return ok([s.DeviceOut.model_validate(d) for d in active_devices(db, user)])


@router.get("/notifications", response_model=Envelope[list[s.NotificationOut]])
def my_notifications(db: DB, user: ApiUser):
    return ok(
        [s.NotificationOut.model_validate(n) for n in notifications.inbox(db, user)],
        unread=notifications.unread_count(db, user),
    )


class ReadIn(BaseModel):
    ids: list[int] | None = None


@router.post("/notifications/read", response_model=Envelope[dict])
def read_notifications(db: DB, user: ApiUser, body: ReadIn):
    notifications.mark_read(db, user, body.ids)
    return ok({"unread": notifications.unread_count(db, user)})


@router.get("/saved", response_model=Envelope[list[s.ListingOut]])
def saved(db: DB, user: ApiUser):
    return ok([s.ListingOut.of(li, next(iter(listing_photos(db, li)), None)) for li in saved_listings(db, user)])


@router.get("/payments", response_model=Envelope[list[s.PaymentOut]])
def payments(db: DB, user: ApiUser):
    """Fees, featured listings and plans this person paid, newest first, each with what it was for."""
    out = []
    for p in payments_for(db, user):
        row = s.PaymentOut.of(p)
        if p.listing_id and (listing := db.get(Listing, p.listing_id)):
            row.subject = f"{listing.reference} · {listing.title}"
        elif p.unit_id and (unit := db.get(Unit, p.unit_id)):
            row.subject = " · ".join(x for x in (unit.digital_address, unit.unit_label) if x)
        out.append(row)
    return ok(out)


@router.get("/units", response_model=Envelope[list[s.MyUnitOut]])
def my_units(db: DB, user: Lister):
    units = db.scalars(select(Unit).where(Unit.registered_by_id == user.id).order_by(Unit.id.desc()))
    return ok([unit_progress(db, u) for u in units])


@router.get("/listings", response_model=Envelope[list[s.ListingOut]])
def my_listings(db: DB, user: Lister):
    rows = db.scalars(
        select(Listing)
        .where(Listing.lister_id == user.id, Listing.status != ListingStatus.ARCHIVED)
        .order_by(Listing.id.desc())
    )
    return ok([s.ListingOut.of(li, next(iter(listing_photos(db, li)), None)) for li in rows])


@router.get("/payouts", response_model=Envelope[s.PayeeOut | None])
def payout_account(db: DB, user: Lister):
    """Where released rent goes. Must match the landlord's verified Ghana Card name."""
    payee = tenancies.active_payee(db, user)
    return ok(_payee_out(payee) if payee else None)


@router.post("/payouts", response_model=Envelope[s.PayeeOut], status_code=201)
def set_payout_account(db: DB, user: Lister, body: s.PayeeIn):
    return ok(_payee_out(tenancies.set_payee(db, user, body.channel, body.account_number, body.code)))


def _payee_out(p) -> s.PayeeOut:
    return s.PayeeOut(id=p.id, channel=p.channel, masked=p.masked, account_name=p.account_name, status=p.status,
                      usable_from=p.usable_from)


@router.get("/export", response_class=JSONResponse)
def export(db: DB, user: ApiUser):
    """Everything Afe holds about you (Act 843), as a JSON file."""
    data = privacy.export_data(db, user)
    db.commit()  # keep the audit record of the export
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="afe-my-data.json"',
                                       "Cache-Control": "no-store"})


@router.post("/close", response_model=Envelope[dict])
def close(db: DB, user: ApiUser, body: s.CloseAccountIn):
    """Close your account. Some records are kept by law; the privacy notice says which and for how long."""
    privacy.close_account(db, user, body.confirm, body.password, body.code)
    return ok({"closed": True})


def _search_out(x) -> s.SavedSearchOut:
    return s.SavedSearchOut(id=x.id, description=alerts.describe_search(x), area_slug=x.area.slug if x.area else None,
                            bedrooms=x.bedrooms, max_rent_pesewas=x.max_rent_pesewas, channel=x.channel,
                            alerts_sent=x.alerts_sent, created_at=x.created_at)


@router.get("/searches", response_model=Envelope[list[s.SavedSearchOut]])
def my_searches(db: DB, user: ApiUser):
    return ok([_search_out(x) for x in alerts.searches_for(db, user)])


@router.post("/searches", response_model=Envelope[s.SavedSearchOut], status_code=201)
def save_search(db: DB, user: ApiUser, body: s.SavedSearchIn):
    area = None
    if body.area_slug:
        area = db.scalar(select(ServiceArea).where(ServiceArea.slug == body.area_slug, ServiceArea.is_active))
        if area is None:
            raise NotFound("Afe isn't open in that area yet.")
    criteria = alerts.Criteria(area, body.bedrooms, body.max_rent_ghs * 100 if body.max_rent_ghs else None)
    return ok(_search_out(alerts.save_search(db, user, criteria, body.channel)))


@router.delete("/searches/{search_id}", response_model=Envelope[dict])
def stop_search(db: DB, user: ApiUser, search_id: int):
    alerts.stop_search(db, user, search_id)
    return ok({"stopped": True})


@router.get("/appealable", response_model=Envelope[list[s.AppealableOut]])
def appealable(db: DB, user: ApiUser):
    return ok([s.AppealableOut(**x) for x in ops.appealable(db, user)])


@router.get("/appeals", response_model=Envelope[list[s.AppealOut]])
def my_appeals(db: DB, user: ApiUser):
    return ok([s.AppealOut.model_validate(a) for a in ops.appeals_for(db, user)])


@router.post("/appeals", response_model=Envelope[s.AppealOut], status_code=201)
def appeal(db: DB, user: ApiUser, body: s.AppealIn):
    return ok(s.AppealOut.model_validate(ops.open_appeal(db, user, body.kind, body.subject_id, body.reason)))


@router.post("/privacy", response_model=Envelope[s.UserOut])
def accept_privacy(db: DB, user: ApiUser):
    """Accept the current privacy notice and terms."""
    return ok(s.UserOut.of(privacy.accept_notice(db, user)))
