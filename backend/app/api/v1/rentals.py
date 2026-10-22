"""Landlord and agent tools (roadmap workstream G): tenant register, rent, receipts, repairs,
agreements, renewals and plans. Tenants with an Afe account see their side too."""

from typing import Annotated

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.core.envelope import Envelope, ok
from app.core.errors import NotFound
from app.deps import DB, ApiUser, Lister
from app.modules.compliance.service import charges_free
from app.modules.rentals import service as rentals
from app.modules.rentals.models import Agreement, Maintenance, Plan, Renewal, RentPayment, Subscription
from app.modules.units.models import Unit

from .. import schemas as s
from .common import MAX_PHOTO_BYTES, get_or_404, read_upload

router = APIRouter(prefix="/rentals", tags=["rentals"])


def _rental_out(r) -> s.RentalOut:
    out = s.RentalOut.model_validate(r)
    out.from_afe, out.tenant_on_afe = r.tenancy_id is not None, r.tenant_user_id is not None
    out.landlord_name, out.home = r.landlord.name, str(r.unit) if r.unit else ""
    return out


def _maint_out(m) -> s.MaintenanceOut:
    out = s.MaintenanceOut.model_validate(m)
    out.has_photo = bool(m.photo_key)
    return out


@router.get("/plan", response_model=Envelope[s.PlanOut])
def plan(db: DB, user: Lister):
    current = rentals.current_plan(db, user)
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    return ok(s.PlanOut(
        plan=current, label=rentals.PLAN_LABELS[Plan(current)], limit=rentals.PLAN_LIMITS[Plan(current)],
        used=rentals._active_count(db, user), period_end=sub.period_end if sub and current != Plan.FREE else None,
        prices={p: rentals.plan_price(db, p) for p in (Plan.STANDARD, Plan.PRO)}, launch_offer=charges_free(db),
    ))


@router.post("/plan/{plan_name}", response_model=Envelope[dict])
def choose_plan(db: DB, user: Lister, plan_name: str):
    payment = rentals.subscribe(db, user, plan_name)
    return ok({"checkout_url": payment.checkout_url if payment else "", "active": payment is None})


@router.get("", response_model=Envelope[list[s.RentalOut]])
def my_rentals(db: DB, user: Lister):
    return ok([_rental_out(r) for r in rentals.rentals_for(db, user)])


@router.get("/my-homes", response_model=Envelope[list[s.RentalOut]])
def homes_i_rent(db: DB, user: ApiUser):
    """For tenants: homes where a landlord keeps a record with your Afe phone number."""
    return ok([_rental_out(r) for r in rentals.homes_rented(db, user)])


@router.get("/agent-homes", response_model=Envelope[list[dict]])
def agent_homes(db: DB, user: Lister):
    return ok([{"owner": g["owner"], "homes": [{"id": u.id, "address": str(u)} for u in g["homes"]]}
               for g in rentals.homes_by_owner(db, user)])


@router.post("", response_model=Envelope[s.RentalOut], status_code=201)
def add(db: DB, user: Lister, body: s.RentalIn):
    unit = get_or_404(db, Unit, body.unit_id, "Home") if body.unit_id else None
    r = rentals.add_rental(db, user, tenant_name=body.tenant_name, tenant_phone=body.tenant_phone,
                           rent_pesewas=body.rent_ghs * 100, pay_every_months=body.pay_every_months,
                           start_date=body.start_date, end_date=body.end_date, unit=unit)
    return ok(_rental_out(r))


@router.get("/{rental_id}", response_model=Envelope[s.RentalDetailOut])
def detail(db: DB, user: ApiUser, rental_id: int):
    r = rentals.get_rental(db, rental_id, user)
    return ok(s.RentalDetailOut(
        rental=_rental_out(r), role="landlord" if user.id == r.landlord_id else "tenant",
        payments=[s.RentPaymentOut.model_validate(p) for p in rentals.payments_for(db, r)],
        maintenance=[_maint_out(m) for m in rentals.maintenance_for(db, r)],
        agreements=[s.AgreementOut.model_validate(a) for a in rentals.agreements_for(db, r)],
        renewals=[s.RenewalOut.model_validate(x) for x in rentals.renewals_for(db, r)],
    ))


@router.post("/{rental_id}/end", response_model=Envelope[s.RentalOut])
def end(db: DB, user: Lister, rental_id: int):
    return ok(_rental_out(rentals.end_rental(db, user, rentals.get_rental(db, rental_id, user))))


@router.post("/{rental_id}/payments", response_model=Envelope[s.RentPaymentOut], status_code=201)
def pay(db: DB, user: Lister, rental_id: int, body: s.RentPaymentIn):
    r = rentals.get_rental(db, rental_id, user)
    p = rentals.record_payment(db, user, r, round(body.amount_ghs * 100), body.paid_on, body.method,
                               body.covers_months, body.note)
    return ok(s.RentPaymentOut.model_validate(p))


@router.get("/{rental_id}/payments/{payment_id}/receipt", response_class=Response)
def receipt(db: DB, user: ApiUser, rental_id: int, payment_id: int):
    r = rentals.get_rental(db, rental_id, user)
    p = get_or_404(db, RentPayment, payment_id, "Payment")
    if p.rental_id != r.id:
        raise NotFound("Payment not found.")
    return Response(rentals.receipt_pdf(db, r, p), media_type="application/pdf",
                    headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{p.receipt_no}.pdf"'})


@router.get("/{rental_id}/invoice", response_class=Response)
def invoice(db: DB, user: ApiUser, rental_id: int):
    """The next rent due as a PDF invoice, for the landlord and the tenant on the record."""
    r = rentals.get_rental(db, rental_id, user)
    return Response(rentals.invoice_pdf(db, r), media_type="application/pdf",
                    headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="rent-invoice-{r.id}.pdf"'})


@router.post("/{rental_id}/maintenance", response_model=Envelope[s.MaintenanceOut], status_code=201)
async def repair(
    db: DB,
    user: ApiUser,
    rental_id: int,
    title: Annotated[str, Form(max_length=120)],
    details: Annotated[str, Form(max_length=4000)],
    photo: UploadFile | None = None,
):
    r = rentals.get_rental(db, rental_id, user)
    data = await read_upload(photo, MAX_PHOTO_BYTES) if photo is not None else None
    return ok(_maint_out(rentals.raise_maintenance(db, user, r, title, details, data)))


@router.post("/maintenance/{request_id}", response_model=Envelope[s.MaintenanceOut])
def repair_status(db: DB, user: Lister, request_id: int, body: s.MaintenanceStatusIn):
    m = get_or_404(db, Maintenance, request_id, "Request")
    return ok(_maint_out(rentals.update_maintenance(db, user, m, body.status, body.note)))


@router.get("/maintenance/{request_id}/photo", response_class=Response)
def repair_photo(db: DB, user: ApiUser, request_id: int):
    from app.modules.media.storage import storage

    m = get_or_404(db, Maintenance, request_id, "Request")
    rentals.get_rental(db, m.rental_id, user)
    if not m.photo_key:
        raise NotFound("No photo.")
    return Response(storage.read("private", m.photo_key), media_type="image/webp", headers={"Cache-Control": "no-store"})


@router.post("/{rental_id}/agreements", response_model=Envelope[s.AgreementOut], status_code=201)
def prepare_agreement(db: DB, user: Lister, rental_id: int):
    return ok(s.AgreementOut.model_validate(rentals.create_agreement(db, user, rentals.get_rental(db, rental_id, user))))


@router.post("/agreements/{agreement_id}/sign", response_model=Envelope[s.AgreementOut])
def sign(db: DB, user: ApiUser, agreement_id: int, body: s.SignIn):
    a = get_or_404(db, Agreement, agreement_id, "Agreement")
    return ok(s.AgreementOut.model_validate(rentals.sign_agreement(db, user, a, body.typed_name)))


@router.get("/agreements/{agreement_id}/pdf", response_class=Response)
def agreement_pdf(db: DB, user: ApiUser, agreement_id: int):
    a = get_or_404(db, Agreement, agreement_id, "Agreement")
    rentals.get_rental(db, a.rental_id, user)
    return Response(rentals.agreement_pdf(a), media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.post("/{rental_id}/renewals", response_model=Envelope[s.RenewalOut], status_code=201)
def offer_renewal(db: DB, user: Lister, rental_id: int, body: s.RenewalIn):
    r = rentals.get_rental(db, rental_id, user)
    return ok(s.RenewalOut.model_validate(
        rentals.offer_renewal(db, user, r, body.new_end_date, body.new_rent_ghs * 100, body.advance_months)))


@router.post("/renewals/{renewal_id}/{answer}", response_model=Envelope[s.RenewalOut])
def decide_renewal(db: DB, user: ApiUser, renewal_id: int, answer: str):
    if answer not in ("accept", "decline"):
        raise NotFound("Not found.")
    rn = get_or_404(db, Renewal, renewal_id, "Renewal")
    return ok(s.RenewalOut.model_validate(rentals.decide_renewal(db, user, rn, answer == "accept")))
