"""Workstream G: landlord and agent tools."""

import dataclasses
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import InvalidInput, NotFound, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.compliance import service as compliance
from app.modules.notifications.providers import fake_outbox
from app.modules.rentals import service as rentals
from app.modules.rentals.models import Plan, Rental, RentPayment
from tests.conftest import api_login, make_user


@pytest.fixture
def tenant(db):
    return make_user(db, "yaa", Role.RENTER, phone="0240000009")


def add(db, landlord, **kw):
    fields = dict(tenant_name="Yaa Mensah", tenant_phone="0240000009", rent_pesewas=300_000, pay_every_months=1,
                  start_date=date(2026, 9, 1), end_date=date(2027, 9, 1))
    fields.update(kw)
    return rentals.add_rental(db, landlord, **fields)


def test_add_months_handles_short_months():
    assert rentals.add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert rentals.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_register_links_the_tenant_account_and_respects_the_plan(db, landlord, tenant):
    r = add(db, landlord)
    assert r.tenant_user_id == tenant.id and r.next_due_date == date(2026, 9, 1)
    with pytest.raises(RuleViolation, match="plan"):
        add(db, landlord, tenant_name="Second tenant", tenant_phone="")
    assert rentals.homes_rented(db, tenant) == [r]


def test_rent_payments_move_the_due_date_and_give_receipts(db, landlord, tenant):
    r = add(db, landlord)
    with pytest.raises(InvalidInput, match="future"):
        rentals.record_payment(db, landlord, r, 300_000, utcnow().date() + timedelta(days=1), "momo", 1)
    p = rentals.record_payment(db, landlord, r, 900_000, date(2026, 9, 1), "momo", 3, "Sep to Nov")
    assert r.next_due_date == date(2026, 12, 1) and p.receipt_no.startswith("AFE-R-")
    assert rentals.receipt_pdf(db, r, p).startswith(b"%PDF")
    other = make_user(db, "kojo", Role.LANDLORD)
    with pytest.raises(NotFound):
        rentals.record_payment(db, other, r, 300_000, date(2026, 9, 1), "cash", 1)


def test_rent_reminders(db, landlord, tenant):
    today = utcnow().date()
    r = add(db, landlord, start_date=today + timedelta(days=5), end_date=today + timedelta(days=400))
    assert rentals.send_rent_reminders(db) == {"due_soon": 1, "overdue": 0}
    assert "due on" in fake_outbox.last("sms", landlord.phone).body
    assert "Your rent" in fake_outbox.last("sms", tenant.phone).body
    assert rentals.send_rent_reminders(db) == {"due_soon": 0, "overdue": 0}  # once per due date
    r.next_due_date = today - timedelta(days=4)
    db.flush()
    assert rentals.send_rent_reminders(db) == {"due_soon": 0, "overdue": 1}
    assert "isn't recorded as paid" in fake_outbox.last("sms", landlord.phone).body


def test_maintenance(db, landlord, tenant):
    r = add(db, landlord)
    m = rentals.raise_maintenance(db, tenant, r, "Leaking tap", "The kitchen tap drips all night.")
    assert "repair" in fake_outbox.last("sms", landlord.phone).body
    rentals.update_maintenance(db, landlord, m, "done", "Plumber fixed it on Saturday")
    assert m.status == "done"
    stranger = make_user(db, "kwesi", Role.RENTER)
    with pytest.raises(NotFound):
        rentals.raise_maintenance(db, stranger, r, "Nope", "Not my home at all really.")


def test_agreement_signed_by_both(db, landlord, tenant):
    r = add(db, landlord)
    a = rentals.create_agreement(db, landlord, r)
    with pytest.raises(InvalidInput, match="full name"):
        rentals.sign_agreement(db, tenant, a, "Somebody Else")
    rentals.sign_agreement(db, landlord, a, landlord.name)
    rentals.sign_agreement(db, tenant, a, tenant.name)
    assert a.landlord_signed_at and a.tenant_signed_at
    assert b"%PDF" in rentals.agreement_pdf(a)[:5]
    a.body += " (edited)"
    with pytest.raises(RuleViolation, match="changed"):
        rentals.sign_agreement(db, tenant, a, tenant.name)


def test_renewal_within_the_advance_cap(db, landlord, tenant):
    r = add(db, landlord)
    with pytest.raises(RuleViolation, match="caps advance rent at 6"):
        rentals.offer_renewal(db, landlord, r, date(2028, 10, 1), 350_000, 12)
    rn = rentals.offer_renewal(db, landlord, r, date(2028, 10, 1), 350_000, 6)
    rentals.decide_renewal(db, tenant, rn, True)
    assert r.end_date == date(2028, 10, 1) and r.rent_pesewas == 350_000


def test_plans_are_free_in_the_launch_offer(db, landlord):
    assert rentals.subscribe(db, landlord, Plan.STANDARD) is None
    assert rentals.current_plan(db, landlord) == Plan.STANDARD


def test_paid_plan_after_the_launch_offer(db, monkeypatch, charges_on, landlord):
    from app.modules.billing.providers import WebhookEvent
    from app.modules.billing.service import apply_webhook

    landlord.created_at = utcnow() - timedelta(days=1)  # joined after the offer ended: no welcome period
    key = "free_period_until"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default="2020-01-01"))
    payment = rentals.subscribe(db, landlord, Plan.PRO)
    assert payment is not None and payment.amount_pesewas == 15_000
    assert rentals.current_plan(db, landlord) == Plan.FREE
    apply_webhook(db, WebhookEvent(payment.reference, True, 15_000, "GHS", {}))
    assert rentals.current_plan(db, landlord) == Plan.PRO


def test_released_afe_tenancy_joins_the_register(db, monkeypatch, verified_unit, verified_landlord, reviewer, tenant):
    from app.config import get_settings
    from app.modules.enquiries import service as enquiries
    from app.modules.listings.service import publish, submit_for_review
    from app.modules.tenancies import service as tenancies
    from app.modules.tenancies.partners import PartnerEvent, TestEscrow
    from tests.conftest import make_listing

    monkeypatch.setattr(get_settings(), "protected_payments_enabled", True)
    TestEscrow.register_name("0244123456", "AMA")
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    publish(db, listing, reviewer)
    viewing = enquiries.request_viewing(db, tenant, listing, utcnow() + timedelta(days=1))
    enquiries.respond_viewing(db, viewing, verified_landlord, True)
    viewing.requested_for = utcnow() - timedelta(hours=2)
    enquiries.complete_viewing(db, viewing, verified_landlord, attended=True)
    tenancies.set_payee(db, verified_landlord, "momo_mtn", "0244123456", "")
    t = tenancies.make_offer(db, verified_landlord, viewing, utcnow().date() + timedelta(days=7), 12, 6, 0)
    tenancies.accept(db, tenant, t)
    ref = TestEscrow.record_charge(t.reference, t.charge_pesewas)
    tenancies.apply_partner_event(db, PartnerEvent("charge.succeeded", t.reference, t.charge_pesewas, ref))
    tenancies.confirm_move_in(db, tenant, t)
    tenancies.approve_release(db, reviewer, t)
    r = db.scalar(select(Rental).where(Rental.tenancy_id == t.id))
    assert r.tenant_user_id == tenant.id and r.next_due_date == rentals.add_months(t.move_in_date, 6)
    paid = db.scalar(select(RentPayment).where(RentPayment.rental_id == r.id))
    assert paid.method == "afe" and paid.amount_pesewas == t.rent_pesewas * 6


def test_rentals_api(client, db, landlord, tenant):
    db.commit()
    h = api_login(client, "ama")
    res = client.post("/api/v1/rentals", headers=h, json={
        "tenant_name": "Yaa Mensah", "tenant_phone": "0240000009", "rent_ghs": 3000, "pay_every_months": 1,
        "start_date": "2026-09-01", "end_date": "2027-09-01"})
    assert res.status_code == 201
    rid = res.json()["data"]["id"]
    res = client.post(f"/api/v1/rentals/{rid}/payments", headers=h,
                      json={"amount_ghs": 3000, "paid_on": "2026-09-01", "method": "cash", "covers_months": 1})
    assert res.status_code == 201
    yaa = api_login(client, "yaa")
    detail = client.get(f"/api/v1/rentals/{rid}", headers=yaa).json()["data"]
    assert detail["role"] == "tenant" and len(detail["payments"]) == 1
    res = client.post(f"/api/v1/rentals/{rid}/maintenance", headers=yaa,
                      data={"title": "Broken window", "details": "The bedroom window latch is broken."})
    assert res.status_code == 201
    plan = client.get("/api/v1/rentals/plan", headers=h).json()["data"]
    assert plan["plan"] == "free" and plan["used"] == 1 and plan["launch_offer"]


def test_receipts_and_invoices_follow_the_document_design(db, landlord, tenant):
    r = add(db, landlord)
    p = rentals.record_payment(db, landlord, r, 300_000, date(2026, 9, 1), "momo", 1)
    receipt = rentals.receipt_pdf(db, r, p)
    assert receipt.startswith(b"%PDF") and b"/Helvetica-Bold" in receipt and b"/Courier" in receipt
    for text in (b"(RECEIPT)", p.receipt_no.encode(), b"(PAID)", b"(Mobile money)", b"(GHS 3,000.00)", b"(Total paid)"):
        assert text in receipt, text
    invoice = rentals.invoice_pdf(db, r)
    for text in (b"(INVOICE)", b"(Amount due)", b"(Yaa Mensah)", f"({r.next_due_date:%d %b %Y})".encode()):
        assert text in invoice, text
    assert b"\xa4" not in receipt + invoice  # the cedi sign becomes "GHS", never an unknown character
    rentals.end_rental(db, landlord, r)
    with pytest.raises(RuleViolation, match="ended"):
        rentals.invoice_pdf(db, r)


def test_documents_over_the_api_and_by_short_lived_link(client, db, landlord, tenant):
    import jwt

    from app.config import get_settings

    r = add(db, landlord)
    p = rentals.record_payment(db, landlord, r, 300_000, date(2026, 9, 1), "cash", 1)
    db.commit()
    ama, yaa = api_login(client, "ama"), api_login(client, "yaa")
    for h in (ama, yaa):
        res = client.get(f"/api/v1/rentals/{r.id}/invoice", headers=h)
        assert res.status_code == 200 and res.headers["content-type"] == "application/pdf" and b"(INVOICE)" in res.content
    stranger = make_user(db, "kojo", Role.RENTER, phone="0240000011")
    db.commit()
    assert client.get(f"/api/v1/rentals/{r.id}/invoice", headers=api_login(client, "kojo")).status_code == 404

    # The app's link: checked when asked for, opened without a sign-in header, bound to one person and file.
    res = client.post("/api/v1/documents/links", headers=yaa, json={"kind": "rent_receipt", "key": f"{r.id}:{p.id}"})
    assert res.status_code == 200
    path = res.json()["data"]["path"]
    doc = client.get(path)
    assert doc.status_code == 200 and b"(RECEIPT)" in doc.content and doc.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/documents/links", headers=api_login(client, "kojo"),
                       json={"kind": "rent_receipt", "key": f"{r.id}:{p.id}"}).status_code == 404
    assert client.post("/api/v1/documents/links", headers=yaa, json={"kind": "anything", "key": "1"}).status_code == 404
    token = path.rsplit("/", 1)[1]
    assert client.get(f"/api/v1/documents/{token[:-2]}xx").status_code == 422  # tampered
    expired = jwt.encode({"sub": str(tenant.id), "typ": "doc", "doc": "rent_invoice", "key": str(r.id), "exp": 1},
                         get_settings().secret_key, algorithm="HS256")
    assert client.get(f"/api/v1/documents/{expired}").status_code == 422
    access = jwt.encode({"sub": str(stranger.id), "typ": "access", "doc": "rent_invoice", "key": str(r.id)},
                        get_settings().secret_key, algorithm="HS256")
    assert client.get(f"/api/v1/documents/{access}").status_code == 422  # a sign-in token is not a document link
