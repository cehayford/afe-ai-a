"""Tenancies and protected payments (Phase 2). Off until protected payments are enabled
(gate B7); the offer, accept and pay calls then refuse with a clear message."""

import json

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response

from app.config import get_settings
from app.core.envelope import Envelope, ok
from app.core.errors import NotFound
from app.core.ghana import format_ghs
from app.db import utcnow
from app.deps import DB, ApiUser, Lister
from app.modules.audit.log import record
from app.modules.audit.webhooks import keep
from app.modules.compliance.service import charges_free, free_until, rule
from app.modules.enquiries.models import Viewing
from app.modules.media.storage import storage
from app.modules.reviews.service import review_for_tenancy, write_review
from app.modules.tenancies import service as tenancies
from app.modules.tenancies.models import Dispute, Tenancy, TenancyStatus
from app.modules.tenancies.partners import PartnerError, PartnerEvent, TestEscrow, get_partner, is_fresh

from .. import schemas as s
from .common import MAX_PHOTO_BYTES, get_or_404, read_upload, refuse, rejected

router = APIRouter(prefix="/tenancies", tags=["tenancies"])


def dispute_out(d: Dispute) -> s.DisputeOut:
    return s.DisputeOut(
        id=d.id, tenancy_reference=d.tenancy.reference, reason=d.reason,
        reason_label=tenancies.DISPUTE_REASONS.get(d.reason, d.reason), details=d.details, status=d.status,
        decision=d.decision, decision_note=d.decision_note, opened_by_name=d.opened_by.name, created_at=d.created_at,
        decided_at=d.decided_at,
    )


def _actions(t: Tenancy, role: str, reviewed: bool) -> list[str]:
    st = TenancyStatus(t.status)
    today = utcnow().date()
    if role == "tenant":
        return {
            TenancyStatus.OFFERED: ["accept", "decline"],
            TenancyStatus.FUNDING: ["pay"],
            TenancyStatus.FUNDED: ["confirm_move_in", "dispute"],
            TenancyStatus.RELEASE_PENDING: ["dispute"],
            TenancyStatus.RELEASED: [] if reviewed else ["review"],
        }.get(st, [])
    if role == "landlord":
        acts = {TenancyStatus.OFFERED: ["withdraw"], TenancyStatus.FUNDED: ["dispute"],
                TenancyStatus.RELEASE_PENDING: ["dispute"]}.get(st, [])
        if st == TenancyStatus.FUNDED and t.move_in_date <= today and not t.landlord_evidence_at:
            acts = ["record_move_in", *acts]
        return acts
    return {TenancyStatus.RELEASE_PENDING: ["approve_release"], TenancyStatus.DISPUTED: ["decide"]}.get(st, [])


def tenancy_out(db, t: Tenancy, user) -> s.TenancyOut:
    role = "tenant" if user.id == t.tenant_id else "landlord" if user.id == t.landlord_id else "reviewer"
    review = review_for_tenancy(db, t)
    dispute = tenancies.dispute_for(db, t)
    return s.TenancyOut(
        reference=t.reference, status=t.status, role=role, actions=_actions(t, role, review is not None),
        listing_reference=t.listing.reference, listing_title=t.listing.title,
        address=f"{t.unit.digital_address} · {t.unit.unit_label}", area=t.unit.area.name,
        landlord_name=t.landlord.name, tenant_name=t.tenant.name, rent_display=format_ghs(t.rent_pesewas),
        advance_months=t.advance_months, deposit_months=t.deposit_months, lease_months=t.lease_months,
        move_in_date=t.move_in_date, held_display=format_ghs(t.held_pesewas), fee_display=format_ghs(t.fee_pesewas),
        fee_pesewas=t.fee_pesewas,
        fee_payer=t.fee_payer, charge_display=format_ghs(t.charge_pesewas), payout_display=format_ghs(t.payout_pesewas),
        charge_pesewas=t.charge_pesewas, held_pesewas=t.held_pesewas, payout_pesewas=t.payout_pesewas,
        offer_expires_at=t.offer_expires_at,
        checkout_url=t.checkout_url if role == "tenant" and t.status == TenancyStatus.FUNDING else "",
        accepted_at=t.accepted_at, funded_at=t.funded_at, tenant_confirmed_at=t.tenant_confirmed_at,
        landlord_evidence_at=t.landlord_evidence_at,
        landlord_evidence=t.landlord_evidence if role != "tenant" or t.status == TenancyStatus.DISPUTED else "",
        closed_at=t.closed_at, close_reason=t.close_reason, has_agreement=bool(t.agreement_key),
        has_receipt=role != "reviewer" and bool(tenancies.receipt_lines(db, t, user)),
        has_move_in_photo=bool(t.move_in_photo_key),
        payee=t.payee.masked if role != "tenant" else "",
        dispute=dispute_out(dispute) if dispute else None,
        review=s.ReviewOut(id=review.id, rating=review.rating, body=review.body, author_name=review.author.name,
                           created_at=review.created_at) if review else None,
    )


@router.get("/config")
def config(db: DB):
    """What the frontend needs to explain protected payments before anyone uses them."""
    return ok({
        "enabled": get_settings().protected_payments_enabled,
        "free_until": free_until(db).isoformat() if charges_free(db) else None,
        "fee_bps": rule(db, "protection_fee_bps"),
        "fee_payer": rule(db, "protection_fee_payer"),
        "advance_cap_months_long": rule(db, "advance_cap_months_long"),
        "advance_cap_months_short": rule(db, "advance_cap_months_short"),
        "max_deposit_months": rule(db, "max_deposit_months"),
    })


@router.get("", response_model=Envelope[list[s.TenancyOut]])
def mine(db: DB, user: ApiUser):
    return ok([tenancy_out(db, t, user) for t in tenancies.tenancies_for(db, user)])


def _offer_viewing(db, user, viewing_id) -> Viewing:
    viewing = get_or_404(db, Viewing, viewing_id, "Viewing")
    if viewing.lister_id != user.id:
        raise NotFound("Viewing not found.")
    return viewing


@router.post("/quote", response_model=Envelope[s.QuoteOut])
def quote(db: DB, user: Lister, body: s.OfferIn):
    """Preview the amounts before offering (no side effects)."""
    viewing = _offer_viewing(db, user, body.viewing_id)
    q = tenancies.quote(db, viewing.listing.rent_pesewas, body.advance_months, body.deposit_months)
    cap = rule(db, "advance_cap_months_long" if body.lease_months > 6 else "advance_cap_months_short")
    return ok(s.QuoteOut(
        held_pesewas=q["held"], fee_pesewas=q["fee"], fee_payer=q["payer"], charge_pesewas=q["charge"],
        payout_pesewas=q["payout"], held_display=format_ghs(q["held"]), fee_display=format_ghs(q["fee"]),
        charge_display=format_ghs(q["charge"]), payout_display=format_ghs(q["payout"]), advance_cap_months=cap,
    ))


@router.post("", response_model=Envelope[s.TenancyOut], status_code=201)
def offer(db: DB, user: Lister, body: s.OfferIn):
    t = tenancies.make_offer(db, user, _offer_viewing(db, user, body.viewing_id), body.move_in_date, body.lease_months,
                             body.advance_months, body.deposit_months)
    return ok(tenancy_out(db, t, user))


@router.get("/{reference}", response_model=Envelope[s.TenancyOut])
def detail(db: DB, user: ApiUser, reference: str):
    return ok(tenancy_out(db, tenancies.get_by_reference(db, reference, user), user))


@router.get("/{reference}/agreement", response_class=Response)
def agreement(db: DB, user: ApiUser, reference: str):
    t = tenancies.get_by_reference(db, reference, user)
    if not t.agreement_key:
        raise NotFound("There is no agreement yet.")
    content = storage.read("private", t.agreement_key)
    record(db, user, "tenancy.agreement_viewed", t)
    db.commit()
    return Response(content, media_type="application/pdf", headers={
        "Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{t.reference}.pdf"'})


@router.get("/{reference}/receipt", response_class=Response)
def receipt(db: DB, user: ApiUser, reference: str):
    t = tenancies.get_by_reference(db, reference, user)
    if user.id not in (t.tenant_id, t.landlord_id):
        raise NotFound("Receipts are for the tenant and landlord.")
    content = tenancies.receipt_pdf(db, t, user)
    return Response(content, media_type="application/pdf", headers={
        "Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{t.reference}-receipt.pdf"'})


@router.post("/{reference}/accept", response_model=Envelope[s.TenancyOut])
def accept(db: DB, user: ApiUser, reference: str):
    """Returns checkout_url: send the tenant there to pay into protection."""
    return ok(tenancy_out(db, tenancies.accept(db, user, tenancies.get_by_reference(db, reference, user, lock=True)), user))


@router.post("/{reference}/decline", response_model=Envelope[s.TenancyOut])
def decline(db: DB, user: ApiUser, reference: str):
    return ok(tenancy_out(db, tenancies.decline(db, user, tenancies.get_by_reference(db, reference, user)), user))


@router.post("/{reference}/withdraw", response_model=Envelope[s.TenancyOut])
def withdraw(db: DB, user: Lister, reference: str):
    return ok(tenancy_out(db, tenancies.withdraw(db, user, tenancies.get_by_reference(db, reference, user)), user))


@router.post("/{reference}/confirm-move-in", response_model=Envelope[s.TenancyOut])
async def confirm_move_in(db: DB, user: ApiUser, reference: str, photo: UploadFile | None = None):
    """Optionally with a photo of the home on the day: evidence if a problem is raised later."""
    data = await read_upload(photo, MAX_PHOTO_BYTES) if photo is not None else None
    t = tenancies.confirm_move_in(db, user, tenancies.get_by_reference(db, reference, user, lock=True), data)
    return ok(tenancy_out(db, t, user))


@router.get("/{reference}/move-in-photo", response_class=Response)
def move_in_photo(db: DB, user: ApiUser, reference: str):
    t = tenancies.get_by_reference(db, reference, user)
    if not t.move_in_photo_key:
        raise NotFound("No move-in photo.")
    content = storage.read("private", t.move_in_photo_key)
    record(db, user, "tenancy.move_in_photo_viewed", t)
    db.commit()
    return Response(content, media_type="image/webp", headers={"Cache-Control": "no-store"})


@router.post("/{reference}/move-in-evidence", response_model=Envelope[s.TenancyOut])
def move_in_evidence(db: DB, user: Lister, reference: str, body: s.EvidenceIn):
    t = tenancies.record_landlord_evidence(db, user, tenancies.get_by_reference(db, reference, user), body.note)
    return ok(tenancy_out(db, t, user))


@router.post("/{reference}/disputes", response_model=Envelope[s.TenancyOut], status_code=201)
def dispute(db: DB, user: ApiUser, reference: str, body: s.DisputeIn):
    t = tenancies.get_by_reference(db, reference, user, lock=True)
    tenancies.open_dispute(db, user, t, body.reason, body.details)
    return ok(tenancy_out(db, t, user))


@router.post("/{reference}/review", response_model=Envelope[s.TenancyOut], status_code=201)
def review(db: DB, user: ApiUser, reference: str, body: s.ReviewIn):
    t = tenancies.get_by_reference(db, reference, user)
    write_review(db, user, t, body.rating, body.body)
    return ok(tenancy_out(db, t, user))


@router.post("/webhook", include_in_schema=False)
async def webhook(db: DB, request: Request):
    """The escrow partner calls this. The partner class checks the signature; a delivery signed more than a few
    minutes ago is refused; every delivery is kept as evidence."""
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    partner = get_partner()
    try:
        event = partner.parse_webhook(body, headers)
    except (PartnerError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return refuse(db, request, partner.name, "tenancies", body, headers, str(exc))
    if event is None:
        keep(db, partner.name, "tenancies", body, headers, "ignored")
        return {"ok": True}
    if not is_fresh(event):
        keep(db, partner.name, "tenancies", body, headers, "stale", reference=event.reference,
             error=f"Signed at {event.sent_at}")
        return rejected("Webhook too old.")
    t = tenancies.apply_partner_event(db, event)
    keep(db, partner.name, "tenancies", body, headers, "applied" if t else "unmatched", reference=event.reference)
    return {"ok": True}


@router.post("/test/{reference}/pay", response_model=Envelope[s.TenancyOut], include_in_schema=False)
def test_pay(db: DB, user: ApiUser, reference: str):
    """Development only: stands in for the partner's checkout and confirmation."""
    settings = get_settings()
    if not settings.debug or not settings.escrow_partner.endswith("TestEscrow"):
        raise NotFound("Not found.")
    t = tenancies.get_by_reference(db, reference, user, lock=True)
    if t.tenant_id != user.id or t.status != TenancyStatus.FUNDING:
        raise NotFound("Nothing to pay.")
    ref = TestEscrow.record_charge(t.reference, t.charge_pesewas)
    tenancies.apply_partner_event(db, PartnerEvent("charge.succeeded", t.reference, t.charge_pesewas, ref))
    return ok(tenancy_out(db, t, user))

