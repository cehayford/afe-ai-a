"""Short-lived links to private documents (receipts, invoices, agreements, the move-in photo) for the
app. A phone can't hand its sign-in token to the PDF viewer or browser that opens the file, so the
app asks for a link here: a signed token, bound to the person and the one document, good for five
minutes. The download re-checks the person's access exactly as the document's own endpoint does."""

import re
from datetime import timedelta

import jwt
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.core.envelope import Envelope, ok
from app.core.errors import InvalidInput, NotFound
from app.db import utcnow
from app.deps import DB, ApiUser
from app.modules.accounts.models import User
from app.modules.audit.log import record
from app.modules.billing.models import Payment
from app.modules.media.storage import storage
from app.modules.rentals import service as rentals
from app.modules.rentals.models import Agreement, RentPayment
from app.modules.tenancies import service as tenancies

router = APIRouter(prefix="/documents", tags=["documents"])

LINK_MINUTES = 5
KINDS = {
    "rent_receipt": r"\d+:\d+",  # rental id : payment id
    "rent_invoice": r"\d+",  # rental id
    "rent_agreement": r"\d+",  # agreement id
    "tenancy_receipt": r"AFE-T-[0-9A-F]{6}",
    "tenancy_agreement": r"AFE-T-[0-9A-F]{6}",
    "move_in_photo": r"AFE-T-[0-9A-F]{6}",
    "fee": r"AFE-[A-Z]+-[0-9A-Z-]{1,40}",  # payment reference
}


class LinkIn(BaseModel):
    kind: str
    key: str = Field(max_length=60)


class LinkOut(BaseModel):
    path: str  # under the API's origin: /api/v1/documents/<token>
    expires_in: int


def render(db, user: User, kind: str, key: str, audit: bool = True) -> tuple[bytes, str, str]:
    """(content, media type, file name), with the same access checks as each document's endpoint.
    `audit` logs opening a private file (agreements, the move-in photo), as their endpoints do."""
    if kind not in KINDS or not re.fullmatch(KINDS[kind], key):
        raise NotFound("Document not found.")
    if kind == "rent_receipt":
        rid, pid = (int(x) for x in key.split(":"))
        r = rentals.get_rental(db, rid, user)
        p = db.get(RentPayment, pid)
        if p is None or p.rental_id != r.id:
            raise NotFound("Payment not found.")
        return rentals.receipt_pdf(db, r, p), "application/pdf", f"{p.receipt_no}.pdf"
    if kind == "rent_invoice":
        r = rentals.get_rental(db, int(key), user)
        return rentals.invoice_pdf(db, r), "application/pdf", f"rent-invoice-{r.id}.pdf"
    if kind == "rent_agreement":
        a = db.get(Agreement, int(key))
        if a is None:
            raise NotFound("Agreement not found.")
        rentals.get_rental(db, a.rental_id, user)
        return rentals.agreement_pdf(a), "application/pdf", f"agreement-{a.id}.pdf"
    if kind == "fee":
        p = db.scalar(select(Payment).where(Payment.reference == key))
        if p is None or (p.user_id != user.id and not user.can_review):
            raise NotFound("Payment not found.")
        from app.modules.documents.render import fee_document

        return fee_document(db, p), "application/pdf", f"{p.reference}.pdf"
    t = tenancies.get_by_reference(db, key, user)
    if kind == "tenancy_receipt":
        if user.id not in (t.tenant_id, t.landlord_id):
            raise NotFound("Receipts are for the tenant and landlord.")
        return tenancies.receipt_pdf(db, t, user), "application/pdf", f"{t.reference}-receipt.pdf"
    if kind == "tenancy_agreement":
        if not t.agreement_key:
            raise NotFound("There is no agreement yet.")
        if audit:
            record(db, user, "tenancy.agreement_viewed", t)
        return storage.read("private", t.agreement_key), "application/pdf", f"{t.reference}.pdf"
    if not t.move_in_photo_key:
        raise NotFound("No move-in photo.")
    if audit:
        record(db, user, "tenancy.move_in_photo_viewed", t)
    return storage.read("private", t.move_in_photo_key), "image/webp", f"{t.reference}-move-in.webp"


@router.post("/links", response_model=Envelope[LinkOut])
def link(db: DB, user: ApiUser, body: LinkIn):
    """A five-minute link to one document this person may open. Checks access now, and again on download."""
    render(db, user, body.kind, body.key, audit=False)
    now = utcnow()
    token = jwt.encode({"sub": str(user.id), "typ": "doc", "doc": body.kind, "key": body.key, "iat": now,
                        "exp": now + timedelta(minutes=LINK_MINUTES)}, get_settings().secret_key, algorithm="HS256")
    return ok(LinkOut(path=f"/api/v1/documents/{token}", expires_in=LINK_MINUTES * 60))


@router.get("/{token}", response_class=Response)
def download(db: DB, token: str):
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        if claims.get("typ") != "doc":
            raise ValueError("not a document link")
        user = db.get(User, int(claims["sub"]))
        kind, key = str(claims["doc"]), str(claims["key"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidInput("This link has expired. Open the document again from the app.") from exc
    if user is None or not user.is_active:
        raise NotFound("Document not found.")
    content, media_type, name = render(db, user, kind, key)
    db.commit()
    return Response(content, media_type=media_type, headers={
        "Cache-Control": "no-store", "Content-Disposition": f'inline; filename="{name}"', "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff"})
