"""Phase 2: protected payments, disputes, reviews, featured listings and compliance rules."""

import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import RateEvent, Role
from app.modules.audit.models import AuditEvent, WebhookReceipt
from app.modules.billing import service as billing
from app.modules.billing.providers import WebhookEvent
from app.modules.compliance import service as compliance
from app.modules.enquiries import service as enquiries
from app.modules.listings.models import ListingStatus
from app.modules.listings.service import publish, search_live, submit_for_review
from app.modules.notifications.providers import fake_outbox
from app.modules.reviews.service import rating_summary, write_review
from app.modules.risk.models import RiskFlag
from app.modules.tenancies import service as tenancies
from app.modules.tenancies.models import LedgerEntry, TenancyStatus
from app.modules.tenancies.partners import PartnerError, PartnerEvent, TestEscrow, Transfer, is_fresh, test_book
from app.modules.units.models import PropertyType
from app.modules.units.service import register_unit
from app.modules.verification.service import decide_unit
from tests.conftest import accept_owner_authority, api_login, make_listing, make_user, passed_visit

WALLET = "0244123456"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "protected_payments_enabled", True)
    test_book.lines.clear()
    test_book.names.clear()
    TestEscrow.register_name(WALLET, "AMA")


@pytest.fixture
def live(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    return publish(db, listing, reviewer)


@pytest.fixture
def renter(db):
    return make_user(db, "yaa", Role.RENTER, phone="0240000009")


@pytest.fixture
def viewed(db, live, renter, verified_landlord):
    viewing = enquiries.request_viewing(db, renter, live, utcnow() + timedelta(days=1))
    enquiries.respond_viewing(db, viewing, verified_landlord, True)
    viewing.requested_for = utcnow() - timedelta(hours=2)
    enquiries.complete_viewing(db, viewing, verified_landlord, attended=True)
    return viewing


@pytest.fixture
def payee(db, verified_landlord):
    return tenancies.set_payee(db, verified_landlord, "momo_mtn", WALLET, "")


def offer(db, viewing, landlord, **kw):
    terms = dict(move_in_date=utcnow().date() + timedelta(days=7), lease_months=12, advance_months=6, deposit_months=0)
    terms.update(kw)
    return tenancies.make_offer(db, landlord, viewing, **terms)


def pay(db, t, amount=None):
    ref = TestEscrow.record_charge(t.reference, amount or t.charge_pesewas)
    return tenancies.apply_partner_event(db, PartnerEvent("charge.succeeded", t.reference, amount or t.charge_pesewas, ref))


@pytest.fixture
def funded(db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    pay(db, t)
    return t


# --- Offers --------------------------------------------------------------------------------------------------


def test_nothing_works_until_protected_payments_are_enabled(db, monkeypatch, viewed, verified_landlord, payee):
    monkeypatch.setattr(get_settings(), "protected_payments_enabled", False)
    with pytest.raises(RuleViolation, match="aren't open yet"):
        offer(db, viewed, verified_landlord)


def test_quote_adds_the_fee_for_the_tenant(db, charges_on):
    q = tenancies.quote(db, 480_000, 6, 1)
    assert q["held"] == 3_360_000
    assert q["fee"] == 117_600  # 3.5%
    assert q["charge"] == q["held"] + q["fee"] and q["payout"] == q["held"]


def test_offer_rules(db, viewed, verified_landlord, payee):
    with pytest.raises(RuleViolation, match="caps advance rent at 6 months"):
        offer(db, viewed, verified_landlord, advance_months=7)
    with pytest.raises(RuleViolation, match="caps advance rent at 2 months"):
        offer(db, viewed, verified_landlord, lease_months=6, advance_months=3)
    with pytest.raises(RuleViolation, match="deposit"):
        offer(db, viewed, verified_landlord, deposit_months=3)
    with pytest.raises(InvalidInput, match="move-in date"):
        offer(db, viewed, verified_landlord, move_in_date=utcnow().date() - timedelta(days=1))
    viewed.listing.rent_pesewas = 1_100_000
    with pytest.raises(RuleViolation, match="pilot"):
        offer(db, viewed, verified_landlord)  # 6 x GH₵11,000 is over the GH₵60,000 pilot cap
    viewed.listing.rent_pesewas = 480_000
    t = offer(db, viewed, verified_landlord)
    assert t.status == TenancyStatus.OFFERED and t.rule_versions["advance_cap_months_long"] == 0
    with pytest.raises(RuleViolation, match="already has a tenancy"):
        offer(db, viewed, verified_landlord)


def test_offer_needs_a_payout_account_and_a_completed_viewing(db, live, renter, verified_landlord):
    viewing = enquiries.request_viewing(db, renter, live, utcnow() + timedelta(days=1))
    with pytest.raises(RuleViolation, match="viewed the home"):
        offer(db, viewing, verified_landlord)
    viewing.status = "completed"
    with pytest.raises(RuleViolation, match="payout account"):
        offer(db, viewing, verified_landlord)


def test_accept_writes_the_agreement_and_opens_checkout(db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    assert t.status == TenancyStatus.FUNDING and t.checkout_url.endswith(t.reference)
    assert t.agreement_key
    assert tenancies.accept(db, renter, t) is t  # a second tap is harmless


def test_expired_offer_cannot_be_accepted(db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    t.offer_expires_at = utcnow() - timedelta(minutes=1)
    with pytest.raises(RuleViolation, match="expired"):
        tenancies.accept(db, renter, t)
    assert t.status == TenancyStatus.EXPIRED


def test_decline_and_withdraw(db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.decline(db, renter, t)
    assert t.status == TenancyStatus.DECLINED
    t2 = offer(db, viewed, verified_landlord)  # a closed offer frees the home for a new one
    tenancies.withdraw(db, verified_landlord, t2)
    assert t2.status == TenancyStatus.WITHDRAWN


# --- Money path ---------------------------------------------------------------------------------------------


def test_payment_confirmation_is_idempotent_and_lets_the_listing(db, funded, live):
    assert funded.status == TenancyStatus.FUNDED and live.status == ListingStatus.LET
    ref = db.scalar(select(LedgerEntry.partner_ref).where(LedgerEntry.kind == "charge_succeeded"))
    tenancies.apply_partner_event(db, PartnerEvent("charge.succeeded", funded.reference, funded.charge_pesewas, ref))
    count = len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == "charge_succeeded")).all())
    assert count == 1


def test_wrong_amount_is_flagged_not_funded(db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    pay(db, t, amount=t.charge_pesewas - 100)
    assert t.status == TenancyStatus.FUNDING
    assert db.scalar(select(RiskFlag).where(RiskFlag.rule == "money.amount_mismatch"))


def test_pilot_release_waits_for_a_reviewer(db, funded, renter, reviewer):
    tenancies.confirm_move_in(db, renter, funded)
    assert funded.status == TenancyStatus.RELEASE_PENDING
    with pytest.raises(NotAllowed):
        tenancies.approve_release(db, renter, funded)
    tenancies.approve_release(db, reviewer, funded, "Tenant confirmed")
    assert funded.status == TenancyStatus.RELEASED
    kinds = [e.kind for e in db.scalars(select(LedgerEntry).where(LedgerEntry.tenancy_id == funded.id))]
    assert kinds[-2:] == ["released", "fee_earned"]
    assert tenancies.reconcile(db) == []


def test_automatic_release_after_the_pilot(db, monkeypatch, funded, renter):
    monkeypatch.setitem(compliance.RULES, "pilot_manual_release",
                        dataclasses.replace(compliance.RULES["pilot_manual_release"], default=False))
    tenancies.confirm_move_in(db, renter, funded)
    assert funded.status == TenancyStatus.RELEASED


def test_undelivered_home_is_refunded_less_gateway_fee(db, charges_on, funded):
    counts = tenancies.run_due(db, today=funded.move_in_date + timedelta(days=4))
    assert counts["refunded"] == 1 and funded.status == TenancyStatus.REFUNDED
    refund = db.scalar(select(LedgerEntry).where(LedgerEntry.kind == "refunded"))
    assert refund.amount_pesewas == funded.charge_pesewas - 56_160  # 1.95% of GH₵28,800 kept by the gateway
    assert funded.listing.status == ListingStatus.PAUSED


def test_landlord_evidence_releases_after_the_fallback_period(db, funded, verified_landlord, reviewer):
    with pytest.raises(RuleViolation, match="on or after"):
        tenancies.record_landlord_evidence(db, verified_landlord, funded, "Keys handed over to Yaa at noon.")
    funded.move_in_date = utcnow().date()
    tenancies.record_landlord_evidence(db, verified_landlord, funded, "Keys handed over to Yaa at noon.")
    assert tenancies.run_due(db, today=funded.move_in_date + timedelta(days=3))["released"] == 0
    tenancies.run_due(db, today=funded.move_in_date + timedelta(days=7))
    assert funded.status == TenancyStatus.RELEASE_PENDING  # pilot: a reviewer still approves


def test_run_due_expires_open_offers(db, viewed, verified_landlord, payee):
    t = offer(db, viewed, verified_landlord)
    t.offer_expires_at = utcnow() - timedelta(minutes=1)
    db.flush()
    assert tenancies.run_due(db)["expired"] == 1 and t.status == TenancyStatus.EXPIRED


# --- Disputes ----------------------------------------------------------------------------------------------


def test_dispute_decided_for_the_tenant_refunds(db, funded, renter, verified_landlord, reviewer):
    d = tenancies.open_dispute(db, renter, funded, "not_as_listed", "There is no water tank, and the roof leaks badly.")
    assert funded.status == TenancyStatus.DISPUTED
    with pytest.raises(RuleViolation):
        tenancies.confirm_move_in(db, renter, funded)
    assert tenancies.run_due(db, today=funded.move_in_date + timedelta(days=30))["refunded"] == 0  # paused
    tenancies.resolve_dispute(db, reviewer, d, "refund", "Photos show the listing was misdescribed.")
    assert funded.status == TenancyStatus.REFUNDED
    with pytest.raises(RuleViolation, match="already decided"):
        tenancies.resolve_dispute(db, reviewer, d, "release", "Changed my mind about this.")


def test_dispute_decided_for_the_landlord_releases(db, funded, verified_landlord, reviewer):
    funded.move_in_date = utcnow().date()
    d = tenancies.open_dispute(db, verified_landlord, funded, "other", "The tenant has moved in but won't confirm.")
    tenancies.resolve_dispute(db, reviewer, d, "release", "Tenant's own photos show them living there.")
    assert funded.status == TenancyStatus.RELEASED


# --- Payout accounts ------------------------------------------------------------------------------------------


def test_payout_account_must_be_in_the_verified_name(db, verified_landlord):
    TestEscrow.register_name("0209998888", "KOFI MENSAH")
    with pytest.raises(RuleViolation, match="registered to KOFI MENSAH"):
        tenancies.set_payee(db, verified_landlord, "momo_telecel", "0209998888", "")


def test_payout_account_needs_verified_identity(db, landlord):
    with pytest.raises(RuleViolation, match="Verify your identity"):
        tenancies.set_payee(db, landlord, "momo_mtn", WALLET, "")


def test_changing_payout_account_starts_a_cooling_off(db, funded, verified_landlord, renter, reviewer):
    TestEscrow.register_name("0551112222", "Ama")
    new = tenancies.set_payee(db, verified_landlord, "momo_mtn", "0551112222", "")
    assert new.usable_from > utcnow() + timedelta(hours=71)
    tenancies.confirm_move_in(db, renter, funded)
    with pytest.raises(RuleViolation, match="cooling-off"):
        tenancies.approve_release(db, reviewer, funded)
    new.usable_from = utcnow() - timedelta(minutes=1)
    tenancies.approve_release(db, reviewer, funded)
    assert funded.status == TenancyStatus.RELEASED and funded.payee_id == new.id


def test_names_match():
    assert tenancies.names_match("Ama Serwaa Owusu", "AMA OWUSU")
    assert tenancies.names_match("Ama Owusu", "OWUSU AMA")
    assert not tenancies.names_match("Ama Owusu", "AMA MENSAH")
    assert not tenancies.names_match("Ama Serwaa Owusu", "AMA")


# --- Reviews ----------------------------------------------------------------------------------------------


def test_reviews_only_after_release(db, funded, renter, reviewer, verified_landlord):
    with pytest.raises(RuleViolation, match="once you've moved in"):
        write_review(db, renter, funded, 5, "Everything was exactly as listed. Would rent again.")
    tenancies.confirm_move_in(db, renter, funded)
    tenancies.approve_release(db, reviewer, funded)
    write_review(db, renter, funded, 4, "Everything was as listed. Water is sometimes off.")
    assert rating_summary(db, verified_landlord.id) == (4.0, 1)
    with pytest.raises(RuleViolation, match="already reviewed"):
        write_review(db, renter, funded, 5, "Changing my review to five stars now.")


# --- Featured listings ------------------------------------------------------------------------------------


def test_featured_listing_comes_first(db, charges_on, live, verified_landlord, area, reviewer, verifier):
    other_unit = register_unit(db, verified_landlord, area, "GA-492-7425", "Flat 3A", live.unit.lat, live.unit.lng,
                               PropertyType.APARTMENT, 2)
    accept_owner_authority(db, other_unit, verified_landlord, reviewer)
    passed_visit(db, other_unit, verifier, seed=5)
    decide_unit(db, other_unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    newer = make_listing(db, other_unit, verified_landlord, title="Newer flat")
    submit_for_review(db, newer, verified_landlord)
    publish(db, newer, reviewer)
    assert search_live(db)[0].id == newer.id

    payment = billing.start_featured(db, verified_landlord, live)
    billing.apply_webhook(db, WebhookEvent(payment.reference, True, payment.amount_pesewas, "GHS", {}))
    assert search_live(db)[0].id == live.id
    assert billing.featured_until(db, live.id) > utcnow() + timedelta(days=13)


# --- Compliance rules -------------------------------------------------------------------------------------


def test_rule_changes_need_a_second_reviewer(db, reviewer):
    second = make_user(db, "reviewer2", Role.REVIEWER)
    row = compliance.propose(db, reviewer, "protection_fee_bps", 300, "Pricing decision, pilot review")
    assert compliance.rule(db, "protection_fee_bps") == 350
    with pytest.raises(RuleViolation):
        compliance.approve(db, row, reviewer)
    compliance.approve(db, row, second)
    assert compliance.rule(db, "protection_fee_bps") == 300
    with pytest.raises(InvalidInput):
        compliance.propose(db, reviewer, "protection_fee_bps", "lots", "Bad value for testing")
    back = compliance.rollback(db, "protection_fee_bps", reviewer)
    compliance.approve(db, back, second)
    assert compliance.rule(db, "protection_fee_bps") == 350


# --- API ----------------------------------------------------------------------------------------------------


def test_tenancy_journey_over_the_api(client, db, viewed, verified_landlord, renter, reviewer):
    landlord_h = api_login(client, "ama")
    res = client.post("/api/v1/me/payouts", headers=landlord_h, json={"channel": "momo_mtn", "account_number": WALLET})
    assert res.status_code == 201, res.text
    terms = {"viewing_id": viewed.id, "move_in_date": str(utcnow().date() + timedelta(days=7)), "lease_months": 12,
             "advance_months": 6, "deposit_months": 0}
    assert client.post("/api/v1/tenancies/quote", headers=landlord_h, json=terms).json()["data"]["charge_display"]
    res = client.post("/api/v1/tenancies", headers=landlord_h, json=terms)
    assert res.status_code == 201, res.text
    ref = res.json()["data"]["reference"]

    renter_h = api_login(client, "yaa")
    t = client.get(f"/api/v1/tenancies/{ref}", headers=renter_h).json()["data"]
    assert t["role"] == "tenant" and t["actions"] == ["accept", "decline"] and t["payee"] == ""
    t = client.post(f"/api/v1/tenancies/{ref}/accept", headers=renter_h).json()["data"]
    assert t["checkout_url"] and t["actions"] == ["pay"]
    pdf = client.get(f"/api/v1/tenancies/{ref}/agreement", headers=renter_h)
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    t = client.post(f"/api/v1/tenancies/test/{ref}/pay", headers=renter_h).json()["data"]
    assert t["status"] == "funded"
    t = client.post(f"/api/v1/tenancies/{ref}/confirm-move-in", headers=renter_h).json()["data"]
    assert t["status"] == "release_pending"

    reviewer_h = api_login(client, "reviewer")
    queue = client.get("/api/v1/review/tenancies", headers=reviewer_h).json()["data"]
    assert [q["reference"] for q in queue] == [ref]
    res = client.post(f"/api/v1/review/tenancies/{ref}/release", headers=reviewer_h,
                      json={"note": "Tenant confirmed move-in."})
    assert res.json()["data"]["status"] == "released"
    assert client.get("/api/v1/review/finance", headers=reviewer_h).json()["meta"]["mismatches"] == []

    res = client.post(f"/api/v1/tenancies/{ref}/review", headers=renter_h,
                      json={"rating": 5, "body": "Exactly as listed and the landlord was helpful."})
    assert res.status_code == 201
    detail = client.get(f"/api/v1/properties/{viewed.listing.reference}")
    assert detail.status_code == 404  # let now, no longer live
    other = make_user(db, "kofi", Role.RENTER)
    db.flush()
    assert client.get(f"/api/v1/tenancies/{ref}", headers=api_login(client, other.username)).status_code == 404


def test_rules_over_the_api(client, db, reviewer):
    make_user(db, "reviewer2", Role.REVIEWER)
    h1, h2 = api_login(client, "reviewer"), api_login(client, "reviewer2")
    rules = client.post("/api/v1/review/rules", headers=h1,
                        json={"key": "offer_valid_hours", "value": 48, "source": "Ops decision, week 3"}).json()["data"]
    pending = next(r for r in rules if r["key"] == "offer_valid_hours")["pending"]
    assert pending and pending[0]["value"] == 48
    assert client.post(f"/api/v1/review/rules/{pending[0]['id']}/approve", headers=h1).status_code == 409
    rules = client.post(f"/api/v1/review/rules/{pending[0]['id']}/approve", headers=h2).json()["data"]
    assert next(r for r in rules if r["key"] == "offer_valid_hours")["value"] == 48


# --- Launch offer: free for the first 8 months of Year 1 --------------------------------------------


def test_launch_offer_makes_every_charge_free(db, viewed, verified_landlord, renter, payee, live):
    from app.modules.compliance.service import charges_free, free_until

    assert charges_free(db) and free_until(db).isoformat() == "2027-06-05"
    assert billing.fee_pesewas(db) == 0
    q = tenancies.quote(db, 480_000, 6, 0)
    assert q["fee"] == 0 and q["charge"] == q["held"] == q["payout"]
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    pay(db, t)
    tenancies.run_due(db, today=t.move_in_date + timedelta(days=4))  # home not handed over
    refund = db.scalar(select(LedgerEntry).where(LedgerEntry.kind == "refunded"))
    assert refund.amount_pesewas == t.charge_pesewas  # refunded in full: Afe absorbs the gateway fee


def test_launch_offer_features_for_free_one_period_at_a_time(db, live, verified_landlord):
    listing = live
    payment = billing.start_featured(db, verified_landlord, listing)
    assert payment.status == "waived" and payment.amount_pesewas == 0 and not payment.checkout_url
    assert billing.featured_until(db, listing.id) is not None
    with pytest.raises(RuleViolation, match="one period at a time"):
        billing.start_featured(db, verified_landlord, listing)


def test_launch_offer_end_date_is_a_rule(db, reviewer):
    from app.modules.compliance import service as compliance

    second = make_user(db, "reviewer2", Role.REVIEWER)
    with pytest.raises(InvalidInput, match="date like"):
        compliance.propose(db, reviewer, "free_period_until", "next summer", "Board decision")
    row = compliance.propose(db, reviewer, "free_period_until", "2026-09-01", "Board ended the offer early")
    compliance.approve(db, row, second)
    assert not compliance.charges_free(db)



def test_pilot_report(db, funded, renter, reviewer):
    from app.modules.notifications.providers import fake_outbox

    admin = make_user(db, "boss", Role.ADMIN, phone="0200000055")
    tenancies.confirm_move_in(db, renter, funded)
    report = tenancies.send_pilot_report(db)
    assert report["funded_today"] == 1 and report["releases_waiting"] == 1
    assert report["held_pesewas"] == funded.held_pesewas and report["reconcile_differences"] == 0
    assert "need a person" in fake_outbox.last("sms", admin.phone).body


def test_suspended_landlord_gets_no_money_until_restored(client, db, funded, renter, reviewer, verified_landlord):
    admin = make_user(db, "boss", Role.ADMIN, phone="0200000056")
    db.commit()
    h = api_login(client, "boss")
    res = client.post(f"/api/v1/admin/people/{verified_landlord.id}/active", headers=h, json={"active": False})
    assert res.status_code == 422  # a reason is required
    res = client.post(f"/api/v1/admin/people/{verified_landlord.id}/active", headers=h,
                      json={"active": False, "reason": "Payout account change reported as not theirs"})
    assert res.json()["data"]["is_active"] is False
    assert client.post(f"/api/v1/admin/people/{reviewer.id}/active", headers=h,
                       json={"active": False, "reason": "Staff go through the staff page"}).status_code == 422
    assert client.post(f"/api/v1/admin/people/{verified_landlord.id}/active", headers=api_login(client, "reviewer"),
                       json={"active": True}).status_code == 403

    db.expire_all()
    t = tenancies.confirm_move_in(db, renter, funded)
    assert t.status == TenancyStatus.RELEASE_PENDING
    with pytest.raises(RuleViolation):
        tenancies.approve_release(db, reviewer, t)
    db.rollback()

    res = client.post(f"/api/v1/admin/people/{verified_landlord.id}/active", headers=h, json={"active": True})
    assert res.json()["data"]["is_active"] is True
    db.expire_all()
    t = db.get(type(funded), funded.id)
    if t.status != TenancyStatus.RELEASE_PENDING:
        t = tenancies.confirm_move_in(db, renter, t)
    assert tenancies.approve_release(db, reviewer, t).status in (TenancyStatus.RELEASING, TenancyStatus.RELEASED)
    assert admin.id


def test_reviewers_see_every_review_and_can_hide_one(client, db, funded, renter, reviewer, verified_landlord, live):
    tenancies.confirm_move_in(db, renter, funded)
    tenancies.approve_release(db, reviewer, funded)
    review = write_review(db, renter, funded, 1, "Call me on 024 000 0000 before you rent from this landlord.")
    h = api_login(client, "reviewer")
    person = client.get(f"/api/v1/review/people/{verified_landlord.id}", headers=h).json()["data"]
    assert [(r["id"], r["hidden"], r["listing_reference"]) for r in person["reviews"]] == [(review.id, False, live.reference)]
    res = client.post(f"/api/v1/review/reviews/{review.id}/hide", headers=h, json={"note": "Contains a phone number"})
    assert res.status_code == 200
    person = client.get(f"/api/v1/review/people/{verified_landlord.id}", headers=h).json()["data"]
    assert person["reviews"][0]["hidden"] is True  # still listed for reviewers...
    assert rating_summary(db, verified_landlord.id) == (None, 0)  # ...but no longer counts for renters


def test_reviewer_revokes_a_verification_over_the_api(client, db, live, verified_landlord, reviewer):
    h = api_login(client, "reviewer")
    vid = client.get(f"/api/v1/review/people/{verified_landlord.id}", headers=h).json()["data"]["current"]["id"]
    res = client.post(f"/api/v1/review/verifications/{vid}/revoke", headers=h, json={"reason_codes": [], "note": ""})
    assert res.status_code >= 400  # a reason code is required
    res = client.post(f"/api/v1/review/verifications/{vid}/revoke", headers=h,
                      json={"reason_codes": ["FRAUD_REPORT"], "note": "Upheld report from a renter"})
    assert res.json()["data"]["status"] == "revoked"
    assert client.get(f"/api/v1/review/people/{verified_landlord.id}", headers=h).json()["data"]["current"] is None
    db.refresh(live)
    assert live.status == ListingStatus.PAUSED


# --- Move-in on WhatsApp ------------------------------------------------------------------------------------------


def whatsapp(client, text, sender="233240000009"):
    body = {"entry": [{"changes": [{"value": {"messages": [{"from": sender, "type": "text", "text": {"body": text}}]}}]}]}
    assert client.post("/api/v1/webhooks/whatsapp", json=body).status_code == 200
    return fake_outbox.last("whatsapp", "+" + sender).body


def test_tenant_confirms_move_in_on_whatsapp(client, db, funded):
    ref = funded.reference
    db.commit()
    reply = whatsapp(client, f"MOVED IN {ref}")
    assert "I have the keys" in reply and f"YES {ref}" in reply
    assert funded.status == TenancyStatus.FUNDED  # nothing happens until YES
    assert "confirmed" in whatsapp(client, f"yes {ref.lower()}")
    assert funded.status == TenancyStatus.RELEASE_PENDING and funded.tenant_confirmed_at
    assert whatsapp(client, f"YES {ref}") == whatsapp(client, "MOVED IN AFE-T-000000")  # nothing more to confirm


def test_move_in_on_whatsapp_needs_the_tenants_number_and_a_fresh_yes(client, db, funded):
    ref = funded.reference
    db.commit()
    made_up = whatsapp(client, "MOVED IN AFE-T-000000")
    assert whatsapp(client, f"MOVED IN {ref}", sender="233244123456") == made_up  # the landlord's number
    assert whatsapp(client, f"YES {ref}", sender="233244123456") == made_up
    assert f"MOVED IN {ref}" in whatsapp(client, f"YES {ref}")  # YES before MOVED IN
    whatsapp(client, f"MOVED IN {ref}")
    db.scalar(select(RateEvent).where(RateEvent.key == f"wa-movein:{ref}")).created_at -= timedelta(minutes=31)
    db.commit()
    assert f"MOVED IN {ref}" in whatsapp(client, f"YES {ref}")  # too late: start again
    assert funded.status == TenancyStatus.FUNDED


def test_a_plain_yes_is_not_a_move_in(client, db, funded):
    db.commit()
    assert "a phone number or listing reference" in whatsapp(client, "Yes")


def test_whatsapp_confirmation_locks_the_tenancy_like_the_tenancy_page(client, db, monkeypatch, funded):
    ref = funded.reference
    db.commit()
    real, locks = tenancies.get_by_reference, []

    def spy(session, reference, user=None, lock=False):
        locks.append(lock)
        return real(session, reference, user, lock)

    monkeypatch.setattr(tenancies, "get_by_reference", spy)
    whatsapp(client, f"MOVED IN {ref}")
    whatsapp(client, f"YES {ref}")
    assert locks and all(locks)  # a second YES waits for the first, then finds nothing waiting


def test_a_refused_payout_on_whatsapp_leaves_the_move_in_unconfirmed(client, db, monkeypatch, funded):
    monkeypatch.setitem(compliance.RULES, "pilot_manual_release",
                        dataclasses.replace(compliance.RULES["pilot_manual_release"], default=False))

    def refuse(*args, **kwargs):
        raise PartnerError("wallet frozen")

    monkeypatch.setattr(TestEscrow, "release", refuse)
    ref = funded.reference
    db.commit()
    whatsapp(client, f"MOVED IN {ref}")
    assert "refused the payout" in whatsapp(client, f"YES {ref}")
    assert funded.status == TenancyStatus.FUNDED and funded.tenant_confirmed_at is None
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "tenancy.move_in_confirmed")) is None


def test_help_mentions_moved_in_while_protected_payments_are_on(client, db):
    assert "MOVED IN" in whatsapp(client, "hello")


def _partner_webhook(client, t, sent_at):
    ref = TestEscrow.record_charge(t.reference, t.charge_pesewas)
    body = {"kind": "charge.succeeded", "reference": t.reference, "amount": t.charge_pesewas, "partner_ref": ref}
    if sent_at is not None:
        body["sent_at"] = sent_at
    return client.post("/api/v1/tenancies/webhook", json=body)


def test_partner_webhooks_are_kept_and_old_ones_refused(client, db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    db.commit()
    for sent_at in [(utcnow() - timedelta(minutes=6)).isoformat(), (utcnow() + timedelta(minutes=6)).isoformat(),
                    "2026-01-01T10:00:00", "yesterday"]:
        assert _partner_webhook(client, t, sent_at).status_code == 422
    assert t.status == TenancyStatus.FUNDING
    assert _partner_webhook(client, t, utcnow().isoformat()).status_code == 200
    assert t.status == TenancyStatus.FUNDED
    receipts = [(r.outcome, r.reference) for r in db.scalars(select(WebhookReceipt).order_by(WebhookReceipt.id))]
    assert receipts == [("stale", t.reference), ("stale", t.reference), ("stale", t.reference),
                        ("rejected", ""), ("applied", t.reference)]


def test_a_partner_event_without_a_signed_send_time_is_refused(client, db, monkeypatch, viewed, verified_landlord,
                                                              renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    db.commit()
    unsigned = PartnerEvent("charge.succeeded", t.reference, t.charge_pesewas, "p-1")
    monkeypatch.setattr(TestEscrow, "parse_webhook", lambda self, body, headers: unsigned)
    assert _partner_webhook(client, t, None).status_code == 422 and t.status == TenancyStatus.FUNDING


# --- Money alarms ---------------------------------------------------------------------------------------------------


@pytest.fixture
def boss(db):
    return make_user(db, "boss", Role.ADMIN, phone="0200000001")


def _admin_texts(boss) -> list[str]:
    return [m.body for m in fake_outbox.messages if m.channel == "sms" and m.recipient == boss.phone]


def test_a_refused_refund_tells_admins_once_and_the_job_carries_on(db, monkeypatch, funded, boss):
    def refuse(*args, **kwargs):
        raise PartnerError("wallet closed")

    monkeypatch.setattr(TestEscrow, "refund", refuse)
    late = funded.move_in_date + timedelta(days=4)
    assert tenancies.run_due(db, today=late)["failed"] == 1
    assert tenancies.run_due(db, today=late)["failed"] == 1  # retried every few minutes, told once
    assert funded.status == TenancyStatus.FUNDED
    flag = db.scalar(select(RiskFlag).where(RiskFlag.rule == "money.refund_failed"))
    assert flag.status == "open" and "wallet closed" in flag.explanation
    texts = _admin_texts(boss)
    assert len(texts) == 1 and "wallet closed" in texts[0] and funded.reference in texts[0]


def test_a_failed_payout_from_the_partner_tells_admins(db, monkeypatch, funded, renter, reviewer, boss):
    monkeypatch.setattr(TestEscrow, "release", lambda self, *a: Transfer("rel-1", completed=False))
    tenancies.confirm_move_in(db, renter, funded)
    tenancies.approve_release(db, reviewer, funded)
    tenancies.apply_partner_event(db, PartnerEvent("release.failed", funded.reference, funded.payout_pesewas, "rel-1"))
    assert any("could not pay the landlord" in t for t in _admin_texts(boss))


def test_reconciliation_differences_reach_admins(db, funded, boss):
    test_book.lines.clear()  # the partner's statement lost the charge
    problems = tenancies.nightly_reconcile(db)
    assert len(problems) == 1
    assert "1 difference" in _admin_texts(boss)[0]


def test_admins_hear_when_held_money_nears_the_pilot_limit(db, monkeypatch, viewed, verified_landlord, renter, payee,
                                                           boss):
    t = offer(db, viewed, verified_landlord)
    monkeypatch.setitem(compliance.RULES, "pilot_max_held_pesewas",
                        dataclasses.replace(compliance.RULES["pilot_max_held_pesewas"], default=int(t.held_pesewas / 0.9)))
    tenancies.accept(db, renter, t)
    assert any("pilot limit" in text for text in _admin_texts(boss))


def test_a_garbled_send_time_is_refused_not_a_crash(client, db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    db.commit()
    assert _partner_webhook(client, t, 12345).status_code == 422
    assert db.scalar(select(WebhookReceipt).where(WebhookReceipt.outcome == "rejected")) is not None
    naive = PartnerEvent("charge.succeeded", t.reference, 1, "p", sent_at=utcnow().replace(tzinfo=None))
    assert is_fresh(naive) is False


def test_a_refund_with_an_unknown_outcome_waits_for_a_person(db, monkeypatch, funded, boss):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("partner timed out")

    monkeypatch.setattr(TestEscrow, "refund", timeout)
    late = funded.move_in_date + timedelta(days=4)
    assert tenancies.run_due(db, today=late)["failed"] == 1
    assert tenancies.run_due(db, today=late)["failed"] == 0 and len(calls) == 1  # not tried again by itself
    assert funded.status == TenancyStatus.FUNDED
    assert db.scalar(select(RiskFlag).where(RiskFlag.rule == "money.refund_unconfirmed")).status == "open"
    assert any("Check with the partner" in text for text in _admin_texts(boss))
