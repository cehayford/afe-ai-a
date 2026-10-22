"""Workstream B: saved searches and alerts, WhatsApp search, viewing reminders, area pages."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import InvalidInput, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.alerts import service as alerts
from app.modules.alerts.models import SavedSearch
from app.modules.enquiries import service as enquiries
from app.modules.listings.service import publish, submit_for_review
from app.modules.notifications.models import Notification
from app.modules.notifications.providers import fake_outbox
from tests.conftest import api_login, make_listing, make_user


@pytest.fixture
def renter(db):
    return make_user(db, "yaa", Role.RENTER, phone="0240000009")


def go_live(db, unit, lister, reviewer, **kw):
    listing = make_listing(db, unit, lister, **kw)
    submit_for_review(db, listing, lister)
    return publish(db, listing, reviewer)


# --- Understanding searches ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "beds", "max_rent", "area_slug"), [
    ("2 bed East Legon under 5000", 2, 500_000, "east-legon"),
    ("single room east legon GH₵800", 0, 80_000, "east-legon"),
    ("4 bedroom house below GHS 12,000", 3, 1_200_000, None),
    ("anything in east legon", None, None, "east-legon"),
])
def test_parse_query(db, area, text, beds, max_rent, area_slug):
    c = alerts.parse_query(db, text)
    assert (c.bedrooms, c.max_rent_pesewas) == (beds, max_rent)
    assert (c.area.slug if c.area else None) == area_slug


def test_describe():
    assert alerts.describe(2, None, 500_000) == "2-bedroom homes in any area up to GH₵5,000/month"
    assert alerts.describe(0, None, None) == "Single rooms in any area"


# --- Saving searches ------------------------------------------------------------------------------------


def test_saving_searches(db, area, renter):
    c = alerts.parse_query(db, "2 bed east legon under 5000")
    s = alerts.save_search(db, renter, c)
    assert s.channel == "sms"
    assert alerts.save_search(db, renter, c, "whatsapp") is s and s.channel == "whatsapp"  # same search, updated
    assert renter.whatsapp_opt_in
    with pytest.raises(InvalidInput, match="Choose an area"):
        alerts.save_search(db, renter, alerts.Criteria())
    for n in range(4):
        alerts.save_search(db, renter, alerts.Criteria(bedrooms=None, max_rent_pesewas=100_000 * (n + 1)))
    with pytest.raises(RuleViolation, match="keep 5 alerts"):
        alerts.save_search(db, renter, alerts.Criteria(bedrooms=1))
    no_phone = make_user(db, "kwesi", Role.RENTER)
    with pytest.raises(InvalidInput, match="phone number"):
        alerts.save_search(db, no_phone, c, "sms")


# --- Sending alerts --------------------------------------------------------------------------------------


def test_alerts_for_new_matching_homes(db, area, renter, verified_unit, verified_landlord, reviewer):
    alerts.save_search(db, renter, alerts.parse_query(db, "2 bed east legon under 5000"))
    listing = go_live(db, verified_unit, verified_landlord, reviewer, rent_pesewas=480_000)
    assert alerts.send_alerts(db) == {"alerts": 1, "paid": 1, "inbox_only": 0}
    sms = fake_outbox.last("sms", renter.phone)
    assert sms.body.startswith("New on Afe: 2-bedroom flat, GH₵4,800/month in East Legon")
    assert f"/homes/{listing.reference}" in sms.body
    assert db.scalar(select(Notification).where(Notification.user_id == renter.id, Notification.channel == "in_app",
                                                Notification.template == "search_alert"))
    assert alerts.send_alerts(db)["alerts"] == 0  # once per home


def test_no_alerts_for_homes_that_do_not_match_or_predate_the_search(db, area, renter, verified_unit,
                                                                      verified_landlord, reviewer):
    go_live(db, verified_unit, verified_landlord, reviewer, rent_pesewas=480_000)
    alerts.save_search(db, renter, alerts.parse_query(db, "2 bed east legon under 5000"))
    assert alerts.send_alerts(db)["alerts"] == 0  # published before the search was saved
    alerts.save_search(db, renter, alerts.parse_query(db, "2 bed under 3000"))
    assert alerts.send_alerts(db)["alerts"] == 0  # too expensive


def test_paid_alerts_are_capped_per_day(db, area, renter, verified_unit, verified_landlord, reviewer):
    s = alerts.save_search(db, renter, alerts.Criteria(area=area))
    s.created_at -= timedelta(days=1)
    listing = go_live(db, verified_unit, verified_landlord, reviewer)
    from app.modules.alerts.models import AlertSent

    for n in range(3):  # three paid alerts already today
        other = make_listing(db, verified_unit, verified_landlord, title=f"Older {n}")
        other.status = "archived"
        db.add(AlertSent(search_id=s.id, listing_id=other.id, channel="sms"))
    db.flush()
    assert alerts.send_alerts(db) == {"alerts": 1, "paid": 0, "inbox_only": 1}
    assert listing.id


# --- WhatsApp -----------------------------------------------------------------------------------------------


def whatsapp(client, text, sender="233240000009"):
    body = {"entry": [{"changes": [{"value": {"messages": [{"type": "text", "from": sender, "text": {"body": text}}]}}]}]}
    assert client.post("/api/v1/webhooks/whatsapp", json=body).status_code == 200
    return fake_outbox.last("whatsapp", "+" + sender).body


def test_whatsapp_find_alert_and_stop(client, db, area, renter, verified_unit, verified_landlord, reviewer):
    listing = go_live(db, verified_unit, verified_landlord, reviewer, rent_pesewas=480_000)
    db.commit()
    reply = whatsapp(client, "FIND 2 bed east legon under 5000")
    assert reply.startswith("Verified homes: 2-bedroom homes in East Legon up to GH₵5,000/month")
    assert f"/homes/{listing.reference}" in reply
    assert "No verified homes match" in whatsapp(client, "find 3 bed east legon under 1000")
    assert "create a free Afe account" in whatsapp(client, "ALERT 2 bed east legon", sender="233550000001")
    assert whatsapp(client, "ALERT 2 bed east legon under 6000").startswith("Done. We'll message you here")
    db.expire_all()
    s = db.scalar(select(SavedSearch).where(SavedSearch.user_id == renter.id))
    assert s.channel == "whatsapp" and s.active
    assert whatsapp(client, "STOP").startswith("Stopped.")
    db.expire_all()
    assert not db.get(SavedSearch, s.id).active
    assert "FIND 2 bed East Legon" in whatsapp(client, "hello")


# --- Viewing reminders --------------------------------------------------------------------------------------


def test_viewing_reminders(db, area, renter, verified_unit, verified_landlord, reviewer):
    listing = go_live(db, verified_unit, verified_landlord, reviewer)
    viewing = enquiries.request_viewing(db, renter, listing, utcnow() + timedelta(hours=23))
    enquiries.respond_viewing(db, viewing, verified_landlord, True)
    assert enquiries.send_viewing_reminders(db) == {"day": 1, "hour": 0}
    assert "tomorrow" in fake_outbox.last("sms", renter.phone).body
    assert "tomorrow" in fake_outbox.last("sms", verified_landlord.phone).body
    assert enquiries.send_viewing_reminders(db) == {"day": 0, "hour": 0}  # not twice
    viewing.requested_for = utcnow() + timedelta(minutes=60)
    db.flush()
    assert enquiries.send_viewing_reminders(db) == {"day": 0, "hour": 1}


# --- Area pages and the searches API -------------------------------------------------------------------------


def test_area_page(client, db, area, verified_unit, verified_landlord, reviewer):
    go_live(db, verified_unit, verified_landlord, reviewer)
    db.commit()
    data = client.get("/api/v1/properties/areas/east-legon").json()["data"]
    assert data["area"]["name"] == "East Legon" and data["live"] == 1 and len(data["listings"]) == 1
    two_bed = next(r for r in data["ranges"] if r["bedrooms"] == 2)
    assert two_bed["source"] == "survey" and two_bed["median"] == 500_000  # fewer than 3 verified listings
    assert client.get("/api/v1/properties/areas/nowhere").status_code == 404


def test_searches_api(client, db, area, renter):
    db.commit()
    h = api_login(client, "yaa")
    res = client.post("/api/v1/me/searches", headers=h,
                      json={"area_slug": "east-legon", "bedrooms": 2, "max_rent_ghs": 5000, "channel": "sms"})
    assert res.status_code == 201
    assert res.json()["data"]["description"] == "2-bedroom homes in East Legon up to GH₵5,000/month"
    sid = res.json()["data"]["id"]
    assert len(client.get("/api/v1/me/searches", headers=h).json()["data"]) == 1
    assert client.delete(f"/api/v1/me/searches/{sid}", headers=h).status_code == 200
    assert client.get("/api/v1/me/searches", headers=h).json()["data"] == []


def test_public_positions_are_approximate(client, db, area, verified_unit, verified_landlord, reviewer):
    go_live(db, verified_unit, verified_landlord, reviewer)
    db.commit()
    home = client.get("/api/v1/properties/search").json()["data"][0]
    assert home["approx_lat"] != float(verified_unit.lat) and abs(home["approx_lat"] - float(verified_unit.lat)) <= 0.0025
    assert round(home["approx_lat"] / 0.005, 6) == round(home["approx_lat"] / 0.005)
