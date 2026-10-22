"""Receipts and invoices as the "Afe Missing Features" canvas draws them (Documents row), written with
the project's dependency-free PDF writer (app/core/pdf.py): rent receipts and rent invoices from the
landlord tools, the protected payment receipt, and invoices and receipts for fees paid to Afe."""

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.pdf import DocItem, Document, document_pdf, ghs
from app.db import utcnow

_METHOD = {"momo": "Mobile money", "bank": "Bank transfer", "cash": "Cash", "afe": "Through Afe"}


def _footer() -> str:
    site = urlparse(get_settings().frontend_url).netloc or "afe"
    return f"Afe · {site} · Generated {utcnow():%d %b %Y, %H:%M} UTC"


def _months(n: int) -> str:
    return f"{n} month{'s' if n != 1 else ''}"


def _home(unit) -> str:
    if unit is None:
        return "Home as agreed between landlord and tenant"
    parts = [unit.unit_label, unit.digital_address, unit.area.name if unit.area else ""]
    return ", ".join(p for p in parts if p)


# --- Landlord tools ------------------------------------------------------------------------------------


def rent_receipt(r, p) -> bytes:
    afe = p.method == "afe"
    return document_pdf(Document(
        kind="RECEIPT",
        number=p.receipt_no,
        facts=[("Paid on", f"{p.paid_on:%d %b %Y}"), ("Method", _METHOD.get(p.method, p.method)), ("Covers", _months(p.covers_months))],
        status=("Paid", "ok"),
        parties=[("Received from (tenant)", r.tenant_name, r.tenant_phone or ""),
                 ("Received by (landlord)", r.landlord.name, _home(r.unit))],
        middle_label="Months",
        items=[DocItem(f"Rent at {ghs(r.rent_pesewas)} a month", ghs(p.amount_pesewas), detail=p.note, middle=str(p.covers_months))],
        summary=[("Subtotal", ghs(p.amount_pesewas))],
        total=("Total paid", ghs(p.amount_pesewas)),
        note_title="Note",
        note="Paid through Afe's protected payment. The money was held by Afe's licensed payment partner until the tenant moved in."
        if afe else "Recorded on Afe by the landlord. Keep this receipt: it is your record of rent paid for this home.",
        footer=_footer(),
    ))


def rent_invoice(r) -> bytes:
    """The next rent due on a tenancy the landlord keeps on Afe, for the tenant."""
    amount = r.rent_pesewas * r.pay_every_months
    today = utcnow().date()
    overdue = r.next_due_date < today
    return document_pdf(Document(
        kind="INVOICE",
        number=f"AFE-RI-{r.id}-{r.next_due_date:%Y%m%d}",
        facts=[("Issued", f"{today:%d %b %Y}"), ("Due", f"{r.next_due_date:%d %b %Y}"), ("Covers", _months(r.pay_every_months))],
        status=("Overdue", "bad") if overdue else (f"Due {r.next_due_date:%d %b}", "warn"),
        parties=[("Bill to (tenant)", r.tenant_name, r.tenant_phone or ""), ("From (landlord)", r.landlord.name, _home(r.unit))],
        middle_label="Months",
        items=[DocItem(f"Rent at {ghs(r.rent_pesewas)} a month, due {r.next_due_date:%d %b %Y}", ghs(amount), middle=str(r.pay_every_months))],
        summary=[("Subtotal", ghs(amount))],
        total=("Amount due", ghs(amount)),
        total_tone="amber",
        note_title="How to pay",
        note=f"Pay {r.landlord.name} as you agreed: mobile money, bank or cash. Your landlord records the payment on Afe and you "
        "get a receipt. Only pay to the details you agreed with your landlord in person.",
        footer=_footer(),
    ))


# --- Protected payments -----------------------------------------------------------------------------------

_HELD = {"funded": ("Held", "warn"), "disputed": ("Held · disputed", "warn"), "release_pending": ("Held", "warn"),
         "releasing": ("Releasing", "warn"), "released": ("Released", "ok"), "refunding": ("Refunding", "quiet"),
         "refunded": ("Refunded", "quiet")}


def tenancy_receipt(db: Session, t, user, lines: list[tuple[str, int, str, str]]) -> bytes:
    """What this person paid in or was paid, from the ledger ([what, pesewas, when, partner ref])."""
    tenant = user.id == t.tenant_id
    home = f"{t.listing.title}, {t.unit.digital_address} {t.unit.unit_label}".strip()
    total = sum(amount for _, amount, _, _ in lines)
    summary = [(f"Rent, {t.advance_months} months in advance", ghs(t.rent_pesewas * t.advance_months))]
    if t.deposit_months:
        summary.append((f"Deposit, {_months(t.deposit_months)}", ghs(t.rent_pesewas * t.deposit_months)))
    summary.append(("Afe protection fee", f"{ghs(t.fee_pesewas)}, {t.fee_payer} pays" if t.fee_pesewas else "None (launch offer)"))
    return document_pdf(Document(
        kind="RECEIPT",
        number=t.reference,
        facts=[("Move-in", f"{t.move_in_date:%d %b %Y}"), ("Lease", _months(t.lease_months)), ("Rent a month", ghs(t.rent_pesewas))],
        status=_HELD.get(t.status, (str(t.status).replace("_", " ").title(), "quiet")),
        parties=[("Tenant", t.tenant.name, "This copy is the tenant's"), ("Landlord and home", t.landlord.name, home)] if tenant
        else [("Landlord", t.landlord.name, "This copy is the landlord's"), ("Tenant and home", t.tenant.name, home)],
        middle_label="When · partner ref",
        middle_width=105,
        items=[DocItem(what, ghs(amount), middle=f"{when}\n{ref or 'n/a'}") for what, amount, when, ref in lines],
        summary=summary,
        total=("Total paid" if tenant else "Total paid to you", ghs(total)),
        note_title="How the money is protected",
        note="Money is held by Afe's licensed payment partner, not by Afe and not by the landlord. It is released to the landlord "
        "when the tenant confirms they have moved in. Keep this receipt with your tenancy agreement.",
        footer=_footer(),
    ))


# --- Fees paid to Afe -------------------------------------------------------------------------------------------

_FEE_STATUS = {"pending": ("Awaiting payment", "warn"), "failed": ("Failed", "bad"), "paid": ("Paid", "ok"), "waived": ("Waived", "quiet")}


def fee_document(db: Session, p) -> bytes:
    """An invoice while a fee waits to be paid (or failed), a receipt once it's paid or waived."""
    from app.modules.compliance.service import rule
    from app.modules.listings.models import Listing

    due = p.status in ("pending", "failed")
    listing = db.get(Listing, p.listing_id) if p.listing_id else None
    if p.purpose == "verification_fee":
        short, what = "Home verification", "Verification fee: an Afe verifier visits the home"
        subject = str(p.unit) if p.unit else ""
    elif p.purpose == "featured_listing":
        short, what = "Featured listing", f"Featured listing: shows first in search for {rule(db, 'featured_days')} days"
        subject = f"{listing.reference} · {listing.title}" if listing else ""
    else:
        plan = p.note.removeprefix("plan:").title() if p.note.startswith("plan:") else "Landlord tools"
        short, what, subject = "Landlord tools", f"{plan} plan for landlord tools, one month", ""
    user = p.user
    contact = " · ".join(x for x in (user.role_label, user.phone or "") if x)
    if due:
        facts = [("Issued", f"{p.created_at:%d %b %Y}"), ("Due", "On receipt"), ("For", short)]
        note_title = "How to pay"
        note = ("Pay in the Afe app or on the website under Fees paid: mobile money (MTN, Telecel, AT) or card through Afe's payment "
                "partner. Afe never asks you to pay to a personal number. A receipt replaces this invoice once the payment is confirmed.")
    else:
        when = p.paid_at or p.created_at
        facts = [("Paid on", f"{when:%d %b %Y}"), ("Method", "Launch offer" if p.status == "waived" else "Payment partner"), ("For", short)]
        note_title = "Note"
        note = p.note if p.note and not p.note.startswith("plan:") else "Thank you. Afe received this payment through its payment partner."
    return document_pdf(Document(
        kind="INVOICE" if due else "RECEIPT",
        number=p.reference,
        facts=facts,
        status=_FEE_STATUS.get(p.status, (p.status.title(), "quiet")),
        parties=[("Bill to" if due else "Paid by", user.name, contact), ("From", "Afe", "Paid through Afe's payment partner")],
        middle_label="Qty",
        items=[DocItem(what, ghs(p.amount_pesewas), detail=subject, middle="1")],
        summary=[("Subtotal", ghs(p.amount_pesewas))],
        total=("Amount due" if due else "Total paid", ghs(p.amount_pesewas)),
        total_tone="amber" if due else "brand",
        note_title=note_title,
        note=note,
        footer=_footer(),
    ))
