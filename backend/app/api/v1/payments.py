"""The verification fee, paid through the partner's hosted checkout."""

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.core.envelope import Envelope, ok
from app.core.errors import NotFound
from app.deps import DB, ApiUser, Lister
from app.modules.audit.webhooks import keep
from app.modules.billing import service as billing
from app.modules.billing.models import Payment
from app.modules.billing.providers import PaymentError, WebhookEvent, get_provider
from app.modules.units.models import Unit

from .. import schemas as s
from .common import get_or_404, refuse

router = APIRouter(prefix="/payments", tags=["payments"])


class FeeIn(BaseModel):
    unit_id: int


@router.post("/verification-fee", response_model=Envelope[s.PaymentOut], status_code=201)
def start_fee(db: DB, user: Lister, body: FeeIn):
    """Returns checkout_url: send the person there to pay by mobile money or card."""
    return ok(s.PaymentOut.of(billing.start_verification_fee(db, user, get_or_404(db, Unit, body.unit_id, "Home"))))


@router.get("/{reference}", response_model=Envelope[s.PaymentOut])
def payment(db: DB, user: ApiUser, reference: str):
    p = db.scalar(select(Payment).where(Payment.reference == reference))
    if p is None or (p.user_id != user.id and not user.can_review):
        raise NotFound("Payment not found.")
    return ok(s.PaymentOut.of(p))


@router.get("/{reference}/document", response_class=Response)
def document(db: DB, user: ApiUser, reference: str):
    """The fee as a PDF: an invoice while it waits to be paid, a receipt once it's paid or waived."""
    from app.modules.documents.render import fee_document

    p = db.scalar(select(Payment).where(Payment.reference == reference))
    if p is None or (p.user_id != user.id and not user.can_review):
        raise NotFound("Payment not found.")
    return Response(fee_document(db, p), media_type="application/pdf",
                    headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{p.reference}.pdf"'})


@router.post("/webhook", include_in_schema=False)
async def webhook(db: DB, request: Request):
    """The payment partner calls this. The provider checks the signature, and every delivery is kept as
    evidence, accepted or not. There's no age check: Paystack signs only the body and resends for up to three
    days, and a resend changes nothing because payments are applied once by reference."""
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    provider = get_provider()
    try:
        event = provider.parse_webhook(body, headers)
    except (PaymentError, ValueError, KeyError, TypeError) as exc:
        return refuse(db, request, provider.name, "fees", body, headers, str(exc))
    if event is None:
        keep(db, provider.name, "fees", body, headers, "ignored")
        return {"ok": True}
    payment = billing.apply_webhook(db, event)
    keep(db, provider.name, "fees", body, headers, "applied" if payment else "unmatched", reference=event.reference)
    return {"ok": True}


@router.post("/test/{reference}/complete", response_model=Envelope[s.PaymentOut], include_in_schema=False)
def complete_test_payment(db: DB, user: ApiUser, reference: str):
    """Development only: stands in for the partner's webhook when using the fake provider."""
    settings = get_settings()
    if not settings.debug or not settings.payment_provider.endswith("FakePayments"):
        raise NotFound("Not found.")
    p = db.scalar(select(Payment).where(Payment.reference == reference, Payment.user_id == user.id))
    if p is None:
        raise NotFound("Payment not found.")
    billing.apply_webhook(db, WebhookEvent(reference, True, p.amount_pesewas, p.currency, {"test": True}))
    return ok(s.PaymentOut.of(p))
