"""Workstream A: real message providers, retries, data rights (Act 843) and staff admin."""

import io
import json
import urllib.error
import urllib.parse
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import NotAllowed, RuleViolation
from app.modules.accounts import privacy, staff
from app.modules.accounts.models import Role, User
from app.modules.audit.models import AuditEvent
from app.modules.enquiries import service as enquiries
from app.modules.listings.service import publish, submit_for_review
from app.modules.notifications import providers
from app.modules.notifications.providers import DeliveryError, HubtelSms, SesEmail, WhatsAppCloud, fake_outbox
from app.modules.notifications.service import notify, retry_failed, send_direct
from app.modules.notifications.whatsapp_templates import whatsapp_template
from app.modules.risk.flags import raise_flag
from tests.conftest import api_login, make_listing, make_user


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def http(monkeypatch):
    """Capture outgoing HTTP requests and answer with a canned JSON body."""
    calls = []
    answer = {"body": {}, "error": None}

    def urlopen(req, timeout=0):
        calls.append(req)
        if answer["error"]:
            raise answer["error"]
        return _Response(json.dumps(answer["body"]).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", urlopen)
    return calls, answer


# --- Providers ---------------------------------------------------------------------------------------------


def test_whatsapp_sends_each_event_through_its_template(monkeypatch, http):
    calls, answer = http
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "1234567890")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "token")
    answer["body"] = {"messages": [{"id": "wamid.ABC"}]}
    wa = whatsapp_template("viewing_confirmed")
    ctx = {"listing": "2 bed\nEast Legon", "when": "Mon 10:00"}
    assert WhatsAppCloud().send_template("+233244123456", wa, ctx) == "wamid.ABC"
    req = calls[0]
    assert req.full_url == "https://graph.facebook.com/v21.0/1234567890/messages"
    assert req.headers["Authorization"] == "Bearer token"
    payload = json.loads(req.data)
    assert payload["to"] == "233244123456" and payload["type"] == "template"
    assert payload["template"] == wa.message(ctx)
    assert payload["template"]["components"][0]["parameters"][0]["text"] == "2 bed · East Legon"


def test_whatsapp_replies_go_as_free_text(monkeypatch, http):
    calls, answer = http
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "1234567890")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "token")
    answer["body"] = {"messages": [{"id": "wamid.R"}]}
    assert WhatsAppCloud().send_text("+233244123456", "Line one\nLine two") == "wamid.R"
    payload = json.loads(calls[0].data)
    assert payload["type"] == "text" and payload["text"] == {"preview_url": False, "body": "Line one\nLine two"}


def test_whatsapp_errors_become_delivery_errors(monkeypatch, http):
    _, answer = http
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "1")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "t")
    answer["error"] = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"error":{"code":131047}}'))
    with pytest.raises(DeliveryError, match="400"):
        WhatsAppCloud().send_text("+233244123456", "hi")
    with pytest.raises(DeliveryError, match="not configured"):
        monkeypatch.setattr(get_settings(), "whatsapp_access_token", "")
        WhatsAppCloud().send_template("+233244123456", whatsapp_template("party_verified"), {})


def test_hubtel_sms(monkeypatch, http):
    calls, answer = http
    monkeypatch.setattr(get_settings(), "hubtel_client_id", "id")
    monkeypatch.setattr(get_settings(), "hubtel_client_secret", "secret")
    answer["body"] = {"status": 0, "messageId": "m-1"}
    assert HubtelSms().send("+233244123456", "Your code is 123456") == "m-1"
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0].full_url).query)
    assert query["to"] == ["233244123456"] and query["from"] == ["Afe"] and query["content"] == ["Your code is 123456"]
    answer["body"] = {"status": 1, "message": "Insufficient balance"}
    with pytest.raises(DeliveryError, match="Insufficient"):
        HubtelSms().send("+233244123456", "hi")


def test_ses_email(monkeypatch):
    import boto3
    from moto import mock_aws

    monkeypatch.setattr(get_settings(), "email_from", "Afe <hello@afe.example>")
    monkeypatch.setattr(get_settings(), "ses_region", "eu-west-1")
    with mock_aws():
        boto3.client("ses", region_name="eu-west-1").verify_email_identity(EmailAddress="hello@afe.example")
        assert SesEmail().send("ama@example.com", "Body", "Subject")


# --- Retries ------------------------------------------------------------------------------------------------


class Flaky:
    name = "flaky-sms"
    fails = 1

    def send(self, recipient, body, title=""):
        if Flaky.fails:
            Flaky.fails -= 1
            raise DeliveryError("gateway timeout")
        return "ok-1"


def test_failed_messages_are_retried_with_a_wait(db, monkeypatch, landlord):
    monkeypatch.setattr(providers, "provider_for", lambda channel: Flaky() if channel == "sms" else None)
    import app.modules.notifications.service as service

    monkeypatch.setattr(service, "provider_for", lambda channel: Flaky() if channel == "sms" else None)
    Flaky.fails = 1
    notes = notify(db, landlord, "review_received", rating=5)
    sms = next(n for n in notes if n.channel == "sms")
    assert sms.status == "failed" and sms.attempts == 1
    assert retry_failed(db) == {"sent": 0, "failed": 0, "waiting": 1}  # 5 minutes haven't passed
    sms.created_at -= timedelta(minutes=6)
    assert retry_failed(db)["sent"] == 1 and sms.status == "sent" and sms.attempts == 2


def test_sign_in_codes_are_never_retried(db, monkeypatch):
    import app.modules.notifications.service as service

    monkeypatch.setattr(service, "provider_for", lambda channel: Flaky())
    Flaky.fails = 5
    note = send_direct(db, "sms", "+233244000111", "otp", code="123456")
    note.created_at -= timedelta(hours=1)
    assert note.status == "failed"
    assert retry_failed(db) == {"sent": 0, "failed": 0, "waiting": 0}


# --- Data rights -----------------------------------------------------------------------------------------------


@pytest.fixture
def conversation(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    publish(db, listing, reviewer)
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    thread = enquiries.start_enquiry(db, renter, listing, "Is the water reliable at night?")
    enquiries.save_listing(db, renter, listing)
    return renter, thread


def test_download_my_data(client, db, conversation):
    renter, _ = conversation
    db.commit()
    res = client.get("/api/v1/me/export", headers=api_login(client, "yaa"))
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    data = res.json()
    assert data["account"]["phone"] == "+233240000009"
    assert data["conversations"][0]["messages"][0]["text"] == "Is the water reliable at night?"
    assert len(data["saved_homes"]) == 1
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "account.data_exported"))


def test_closing_an_account(client, db, conversation):
    renter, thread = conversation
    db.commit()
    h = api_login(client, "yaa")
    assert client.post("/api/v1/me/close", headers=h, json={"confirm": "yes"}).status_code == 409
    assert client.post("/api/v1/me/close", headers=h, json={"confirm": "DELETE", "password": "wrong"}).status_code == 409
    res = client.post("/api/v1/me/close", headers=h, json={"confirm": "DELETE", "password": "x-test-password"})
    assert res.status_code == 200
    db.expire_all()
    user = db.get(User, renter.id)
    assert user.username == f"closed-{renter.id}" and user.phone is None and not user.is_active
    assert thread.messages[0].body == privacy.CLOSED_MESSAGE
    assert client.get("/api/v1/me", headers=h).status_code == 401  # signed out everywhere
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "account.closed"))


def test_accounts_under_review_or_staff_cannot_self_close(db, verified_landlord, reviewer):
    raise_flag(db, verified_landlord, "report.upheld", "high", "Scam report upheld")
    with pytest.raises(RuleViolation, match="trust team"):
        privacy.close_account(db, verified_landlord, "DELETE", password="x-test-password")
    with pytest.raises(RuleViolation, match="Staff accounts"):
        privacy.close_account(db, reviewer, "DELETE", password="x-test-password")


# --- Staff admin ---------------------------------------------------------------------------------------------


@pytest.fixture
def admin(db):
    return make_user(db, "boss", Role.ADMIN)


def test_admin_adds_and_manages_staff(db, admin, reviewer):
    with pytest.raises(NotAllowed):
        staff.add_staff(db, reviewer, "Kwame Boateng", "0200000077", "field_verifier")
    new = staff.add_staff(db, admin, "Kwame Boateng", "0200000077", "field_verifier")
    assert new.role == "field_verifier" and new.password_hash == ""
    assert fake_outbox.last("sms", "+233200000077").body.startswith("Hi Kwame, you've been added")
    with pytest.raises(RuleViolation, match="already has an Afe account"):
        staff.add_staff(db, admin, "Someone Else", "0200000077", "reviewer")
    staff.change_role(db, admin, new, "reviewer")
    staff.set_active(db, admin, new, False)
    assert not new.is_active
    with pytest.raises(RuleViolation, match="your own"):
        staff.set_active(db, admin, admin, False)


def test_afe_always_keeps_an_active_admin(db, admin):
    other = make_user(db, "boss2", Role.ADMIN)
    staff.set_active(db, admin, other, False)
    with pytest.raises(RuleViolation, match="at least one active admin"):
        staff.change_role(db, other, admin, "reviewer")  # other is inactive, but the rule counts active admins
    staff.set_active(db, admin, other, True)
    staff.change_role(db, other, admin, "reviewer")
    assert admin.role == "reviewer"


def test_staff_over_the_api(client, db, admin, reviewer):
    db.commit()
    h = api_login(client, "boss")
    assert client.get("/api/v1/admin/staff", headers=api_login(client, "reviewer")).status_code == 403
    res = client.post("/api/v1/admin/staff", headers=h,
                      json={"name": "Akosua Darko", "phone": "0200000088", "role": "field_verifier"})
    assert res.status_code == 201
    staff_id = res.json()["data"]["id"]
    rows = client.get("/api/v1/admin/staff", headers=h).json()["data"]
    assert {r["username"] for r in rows} >= {"boss", "reviewer", "staff-200000088"}
    reviewer_h = api_login(client, "reviewer")
    res = client.post(f"/api/v1/admin/staff/{reviewer.id}/active", headers=h, json={"active": False})
    assert res.json()["data"]["is_active"] is False
    assert client.get("/api/v1/me", headers=reviewer_h).status_code == 401  # locked out at once
    assert staff_id
