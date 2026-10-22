"""Saved homes, enquiries, messages and viewings."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.errors import InvalidInput, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.enquiries import service as enquiries
from app.modules.enquiries.models import ViewingStatus
from app.modules.listings.service import publish, submit_for_review
from app.modules.notifications.models import Notification
from app.modules.notifications.providers import fake_outbox
from app.modules.risk.flags import open_flags
from tests.conftest import api_login, make_listing, make_user


@pytest.fixture
def live(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    return publish(db, listing, reviewer)


@pytest.fixture
def renter(db):
    return make_user(db, "yaa", Role.RENTER, phone="0240000009")


def test_save_and_unsave(db, live, renter):
    enquiries.save_listing(db, renter, live)
    enquiries.save_listing(db, renter, live)  # idempotent
    assert enquiries.saved_listings(db, renter) == [live]
    enquiries.unsave_listing(db, renter, live)
    assert enquiries.saved_listings(db, renter) == []


def test_enquiry_opens_a_thread_and_tells_the_lister(db, live, renter, verified_landlord):
    thread = enquiries.start_enquiry(db, renter, live, "Is it still available?")
    assert [m.body for m in thread.messages] == ["Is it still available?"]
    assert thread.unread_for(verified_landlord) and not thread.unread_for(renter)
    assert fake_outbox.last("sms", verified_landlord.phone).body.startswith("Yaa sent you a message")

    # A burst of messages sends one SMS, not one per message.
    fake_outbox.clear()
    enquiries.send_message(db, thread, renter, "Also, is there parking?")
    assert fake_outbox.last("sms", verified_landlord.phone) is None


def test_listers_asking_for_money_first_are_warned_and_flagged(db, live, renter, verified_landlord):
    thread = enquiries.start_enquiry(db, renter, live, "Can I see it on Saturday?")
    reply = enquiries.send_message(db, thread, verified_landlord, "Pay the viewing fee first, then we can go.")
    assert "Never pay before you view" in reply.warning
    assert [f.rule for f in open_flags(db, verified_landlord)] == ["message.language.pay_before_viewing"]


def test_you_cannot_enquire_about_your_own_listing(db, live, verified_landlord, reviewer):
    with pytest.raises(RuleViolation):
        enquiries.start_enquiry(db, verified_landlord, live, "Hello")


def test_viewing_journey(db, live, renter, verified_landlord):
    with pytest.raises(InvalidInput, match="at least an hour"):
        enquiries.request_viewing(db, renter, live, utcnow() + timedelta(minutes=10))
    viewing = enquiries.request_viewing(db, renter, live, utcnow() + timedelta(days=1), "After 5pm is best")
    assert fake_outbox.last("sms", verified_landlord.phone).body.startswith("Yaa asked to view")
    with pytest.raises(RuleViolation, match="already have a viewing"):
        enquiries.request_viewing(db, renter, live, utcnow() + timedelta(days=2))

    with pytest.raises(RuleViolation):
        enquiries.complete_viewing(db, viewing, verified_landlord, True)  # not confirmed yet
    enquiries.respond_viewing(db, viewing, verified_landlord, True)
    assert viewing.status == ViewingStatus.CONFIRMED
    assert "confirmed" in fake_outbox.last("sms", renter.phone).body
    with pytest.raises(RuleViolation, match="after it has happened"):
        enquiries.complete_viewing(db, viewing, verified_landlord, True)

    viewing.requested_for = utcnow() - timedelta(hours=2)
    enquiries.complete_viewing(db, viewing, verified_landlord, attended=True)
    assert viewing.status == ViewingStatus.COMPLETED
    thread = enquiries.open_thread(db, viewing.thread_id, renter)
    system = [m.body for m in thread.messages if m.sender_id is None]
    assert any("asked to view" in b for b in system) and any("confirmed" in b for b in system)


def test_either_side_can_cancel(db, live, renter, verified_landlord):
    viewing = enquiries.request_viewing(db, renter, live, utcnow() + timedelta(days=1))
    enquiries.cancel_viewing(db, viewing, renter)
    assert viewing.status == ViewingStatus.CANCELLED
    with pytest.raises(RuleViolation):
        enquiries.cancel_viewing(db, viewing, verified_landlord)


def test_messaging_over_the_api(client, db, live, renter, verified_landlord):
    db.commit()
    yaa, ama = api_login(client, "yaa"), api_login(client, "ama")
    ref = live.reference

    assert client.post(f"/api/v1/properties/{ref}/save", headers=yaa).json()["data"] == {"saved": True}
    assert client.get(f"/api/v1/properties/{ref}", headers=yaa).json()["data"]["saved"] is True
    assert [li["reference"] for li in client.get("/api/v1/me/saved", headers=yaa).json()["data"]] == [ref]

    thread = client.post(
        f"/api/v1/properties/{ref}/enquiries", headers=yaa, json={"body": "Hello, is it free?"}
    ).json()["data"]
    assert thread["role"] == "renter"
    client.post(f"/api/v1/messages/{thread['id']}", headers=ama, json={"body": "Yes. WhatsApp me on 024 111 2222"})
    detail = client.get(f"/api/v1/messages/{thread['id']}", headers=yaa).json()["data"]
    assert [m["sender"] for m in detail["messages"]] == ["You", "Ama"]
    assert "keep the conversation and any payment on Afe" in detail["messages"][1]["warning"]
    # The sender never sees a warning on their own message.
    assert client.get(f"/api/v1/messages/{thread['id']}", headers=ama).json()["data"]["messages"][1]["warning"] == ""

    when = (utcnow() + timedelta(days=3)).isoformat()
    viewing = client.post(f"/api/v1/properties/{ref}/viewings", headers=yaa, json={"when": when}).json()["data"]
    assert viewing["status"] == "requested"
    assert (
        client.post(f"/api/v1/viewings/{viewing['id']}/respond", headers=yaa, json={"confirm": True}).status_code == 403
    )
    ok = client.post(f"/api/v1/viewings/{viewing['id']}/respond", headers=ama, json={"confirm": True}).json()["data"]
    assert ok["status"] == "confirmed"

    other = make_user(db, "stranger", Role.RENTER)
    db.commit()
    assert client.get(f"/api/v1/messages/{thread['id']}", headers=api_login(client, "stranger")).status_code == 404
    assert other.id


def test_notifications_inbox(client, db, live, renter):
    enquiries.start_enquiry(db, renter, live, "Hi")
    db.commit()
    ama = api_login(client, "ama")
    inbox = client.get("/api/v1/me/notifications", headers=ama).json()
    assert inbox["meta"]["unread"] >= 1
    assert any(n["link"].startswith("/account/messages/") for n in inbox["data"])
    assert client.post("/api/v1/me/notifications/read", headers=ama, json={}).json()["data"]["unread"] == 0
    total = db.scalar(select(func.count()).select_from(Notification))
    assert total > 0
