"""Workstreams E (insights), D (move-in photo) and H (opening new areas)."""

from datetime import timedelta

import pytest

from app.config import get_settings
from app.core.errors import NotAllowed, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.areas import service as areas
from app.modules.enquiries import service as enquiries
from app.modules.insights import service as insights
from app.modules.listings.service import publish, submit_for_review
from tests.conftest import api_login, begin_visit, make_listing, make_user, photo_bytes


@pytest.fixture
def renter(db):
    return make_user(db, "yaa", Role.RENTER, phone="0240000009")


@pytest.fixture
def live(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    return publish(db, listing, reviewer)


def completed_viewing(db, renter, listing, lister):
    viewing = enquiries.request_viewing(db, renter, listing, utcnow() + timedelta(days=1))
    enquiries.respond_viewing(db, viewing, lister, True)
    viewing.requested_for = utcnow() - timedelta(hours=2)
    enquiries.complete_viewing(db, viewing, lister, attended=True)
    return viewing


# --- Leakage ------------------------------------------------------------------------------------------------


def test_viewing_outcomes_measure_leakage(db, live, renter, verified_landlord):
    viewing = completed_viewing(db, renter, live, verified_landlord)
    with pytest.raises(RuleViolation):
        insights.record_outcome(db, renter, viewing, "maybe")
    insights.record_outcome(db, renter, viewing, "paid_directly")
    insights.record_outcome(db, renter, viewing, "rented_through_afe")  # changed their answer
    assert insights.leakage(db)["answers"]["rented_through_afe"] == 1
    assert insights.leakage(db)["rate"] == 0.0


def test_outcome_over_the_api(client, db, live, renter, verified_landlord):
    viewing = completed_viewing(db, renter, live, verified_landlord)
    db.commit()
    h = api_login(client, "yaa")
    res = client.post(f"/api/v1/viewings/{viewing.id}/outcome", headers=h, json={"answer": "still_deciding"})
    assert res.status_code == 200 and res.json()["data"]["outcome"] == "still_deciding"
    ama = api_login(client, "ama")
    assert client.post(f"/api/v1/viewings/{viewing.id}/outcome", headers=ama, json={"answer": "not_renting"}).status_code == 404


# --- Cost per verification ------------------------------------------------------------------------------------


def test_verification_cost(db, monkeypatch, unit, verifier):
    from app.modules.verification.service import complete_visit

    monkeypatch.setattr(get_settings(), "verification_fee_pesewas", 20_000)
    visit = begin_visit(db, unit, verifier)
    visit.started_at = utcnow() - timedelta(minutes=60)
    complete_visit(db, visit, verifier, {"unit_exists": False}, travel_minutes=60, transport_pesewas=3_000)
    cost = insights.verification_cost(db)
    assert cost["visits_measured"] == 1
    assert 7_900 <= cost["median_pesewas"] <= 8_100  # 2 hours at GH₵25 plus GH₵30 fares
    assert cost["within_fee"] is True


# --- Targets and the rent index -------------------------------------------------------------------------------


def test_targets(db, live):
    rows = {r["name"]: r for r in insights.targets(db)}
    assert rows["Verified listings live"]["value"] == 1 and rows["Verified listings live"]["met"] is False
    assert rows["Confirmed fraud on verified listings"]["met"] is True


def test_rent_index_needs_three_homes(client, db, live):
    db.commit()
    data = client.get("/api/v1/properties/rent-index").json()["data"]
    assert data["areas"] == []  # one home isn't enough to publish a figure
    assert data["period_days"] == 90


def test_targets_api(client, db, reviewer, live):
    db.commit()
    rows = client.get("/api/v1/review/targets", headers=api_login(client, "reviewer")).json()["data"]
    assert any(r["name"] == "Verified listings live" for r in rows)


# --- Move-in photo --------------------------------------------------------------------------------------------


def test_move_in_photo_is_kept_privately(client, db, monkeypatch, live, renter, verified_landlord):
    from app.modules.tenancies import service as tenancies
    from app.modules.tenancies.partners import PartnerEvent, TestEscrow

    monkeypatch.setattr(get_settings(), "protected_payments_enabled", True)
    TestEscrow.register_name("0244123456", "AMA")
    viewing = completed_viewing(db, renter, live, verified_landlord)
    tenancies.set_payee(db, verified_landlord, "momo_mtn", "0244123456", "")
    t = tenancies.make_offer(db, verified_landlord, viewing, utcnow().date() + timedelta(days=7), 12, 6, 0)
    tenancies.accept(db, renter, t)
    ref = TestEscrow.record_charge(t.reference, t.charge_pesewas)
    tenancies.apply_partner_event(db, PartnerEvent("charge.succeeded", t.reference, t.charge_pesewas, ref))
    db.commit()
    h = api_login(client, "yaa")
    res = client.post(f"/api/v1/tenancies/{t.reference}/confirm-move-in", headers=h,
                      files={"photo": ("home.jpg", photo_bytes(3), "image/jpeg")})
    assert res.status_code == 200 and res.json()["data"]["has_move_in_photo"]
    img = client.get(f"/api/v1/tenancies/{t.reference}/move-in-photo", headers=api_login(client, "ama"))
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    assert b"Exif" not in img.content


# --- Opening areas ---------------------------------------------------------------------------------------------


MADINA = [[5.66, -0.18], [5.66, -0.15], [5.69, -0.15], [5.69, -0.18]]


def test_opening_an_area_needs_boundary_survey_and_verifier(db, reviewer):
    admin = make_user(db, "boss", Role.ADMIN)
    with pytest.raises(NotAllowed):
        areas.create_area(db, reviewer, "Madina", "madina", "Accra", MADINA)
    area = areas.create_area(db, admin, "Madina", "madina", "Accra", MADINA)
    assert not area.is_active
    with pytest.raises(RuleViolation, match="price survey for at least 2 home sizes, an active field verifier"):
        areas.set_open(db, admin, area, True)
    areas.load_price_survey(db, admin, area, [
        {"bedrooms": 1, "low_ghs": 1500, "median_ghs": 2200, "high_ghs": 3000},
        {"bedrooms": 2, "low_ghs": 2500, "median_ghs": 3500, "high_ghs": 5000},
    ])
    make_user(db, "verifier", Role.FIELD_VERIFIER)
    areas.set_open(db, admin, area, True)
    assert area.is_active


def test_area_validation(db):
    admin = make_user(db, "boss", Role.ADMIN)
    from app.core.errors import InvalidInput

    with pytest.raises(InvalidInput, match="inside Ghana"):
        areas.create_area(db, admin, "London", "london", "London", [[51.5, -0.1], [51.6, -0.1], [51.6, 0.0]])
    area = areas.create_area(db, admin, "Madina", "madina", "Accra", MADINA)
    with pytest.raises(InvalidInput, match="must rise"):
        areas.load_price_survey(db, admin, area, [{"bedrooms": 1, "low_ghs": 3000, "median_ghs": 2000, "high_ghs": 4000}])
