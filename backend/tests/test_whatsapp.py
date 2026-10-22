"""WhatsApp go-live: a template per event, free-form replies, delivery reports, WhatsApp first with SMS as the
fallback, the opt-in record, and alarms on the number's health."""

import io
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.cli import main
from app.config import get_settings
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.accounts.service import set_whatsapp_opt_in
from app.modules.alerts import service as alerts
from app.modules.audit.models import AuditEvent
from app.modules.notifications import providers, service
from app.modules.notifications.alarms import whatsapp_health
from app.modules.notifications.models import Notification
from app.modules.notifications.providers import fake_outbox
from app.modules.notifications.service import (
    MAX_ATTEMPTS,
    TEMPLATES,
    apply_whatsapp_status,
    expire_undelivered,
    notify,
    notify_on,
    retry_failed,
    send_direct,
)
from app.modules.notifications.whatsapp_templates import (
    AUTHENTICATION,
    MARKETING,
    NOT_ON_WHATSAPP,
    SAMPLES,
    UTILITY,
    registry,
    sync_all,
    whatsapp_template,
)
from tests.conftest import api_login, make_user


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def graph(monkeypatch):
    """Meta's Graph API: records each request and answers with the next canned body (or raises it)."""
    calls, answers = [], []

    def urlopen(req, timeout=0):
        calls.append(req)
        answer = answers.pop(0) if answers else {}
        if isinstance(answer, Exception):
            raise answer
        return _Response(json.dumps(answer).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(get_settings(), "whatsapp_business_account_id", "waba-1")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "token")
    return calls, answers


# --- Templates ---------------------------------------------------------------------------------------------


def test_every_message_has_a_whatsapp_template_or_a_reason_not_to():
    for key in TEMPLATES:
        assert (whatsapp_template(key) is None) == (key in NOT_ON_WHATSAPP), key


def test_templates_follow_metas_rules():
    for wa in registry().values():
        assert re.fullmatch(r"afe_[a-z0-9_]+", wa.name), wa.name
        if wa.category == AUTHENTICATION:
            continue
        assert not wa.body.startswith("{{") and not wa.body.endswith("}}"), wa.name  # Meta refuses both
        assert re.findall(r"\{\{(\w+)\}\}", wa.body) == list(wa.params), wa.name
        assert all(p in SAMPLES for p in wa.params), wa.name


def test_categories_and_names():
    assert whatsapp_template("otp").category == AUTHENTICATION
    assert whatsapp_template("otp").name == "afe_sign_in_code"
    assert whatsapp_template("search_alert").category == MARKETING
    assert whatsapp_template("viewing_confirmed").category == UTILITY
    assert whatsapp_template("viewing_confirmed").name == "afe_viewing_confirmed"


def test_a_text_that_starts_with_a_name_gets_a_prefix():
    wa = whatsapp_template("new_message")
    assert wa.body == "Afe: {{sender}} sent you a message about {{listing}} on Afe."
    assert wa.render({"sender": "Yaa", "listing": "2 bed, East Legon"}) == (
        "Afe: Yaa sent you a message about 2 bed, East Legon on Afe."
    )


def test_parameters_are_cleaned_for_meta():
    wa = whatsapp_template("maintenance_raised")
    message = wa.message({"tenant": "Yaa", "title": "Leak\nin the\tkitchen" + " " * 8 + "sink"})
    assert message["name"] == "afe_maintenance_raised" and message["language"] == {"code": "en"}
    assert message["components"] == [{"type": "body", "parameters": [
        {"type": "text", "parameter_name": "tenant", "text": "Yaa"},
        {"type": "text", "parameter_name": "title", "text": "Leak · in the · kitchen   sink"},
    ]}]
    assert wa.values({"tenant": "  ", "title": "x"})["tenant"] == "-"  # Meta refuses an empty parameter
    with pytest.raises(providers.DeliveryError, match="needs title"):
        wa.message({"tenant": "Yaa"})


def test_sign_in_codes_use_metas_authentication_template():
    wa = whatsapp_template("otp")
    code = [{"type": "text", "text": "123456"}]
    assert wa.message({"code": "123456"})["components"] == [
        {"type": "body", "parameters": code},
        {"type": "button", "sub_type": "url", "index": "0", "parameters": code},
    ]
    assert wa.submission()["components"] == [
        {"type": "BODY", "add_security_recommendation": True},
        {"type": "FOOTER", "code_expiration_minutes": get_settings().otp_minutes},
        {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
    ]
    assert wa.render({"code": "123456"}).startswith("123456 is your verification code.")


def test_a_utility_submission_has_named_examples():
    sub = whatsapp_template("viewing_confirmed").submission()
    assert sub["category"] == UTILITY and sub["parameter_format"] == "named" and sub["language"] == "en"
    assert sub["components"] == [{
        "type": "BODY",
        "text": "Your viewing of {{listing}} is confirmed for {{when}}. Never pay before you view.",
        "example": {"body_text_named_params": [
            {"param_name": "listing", "example": SAMPLES["listing"]},
            {"param_name": "when", "example": SAMPLES["when"]},
        ]},
    }]
    plain = whatsapp_template("account_restored").submission()
    assert "parameter_format" not in plain and "example" not in plain["components"][0]
    alert = whatsapp_template("search_alert").submission()
    title = alert["components"][0]["example"]["body_text_named_params"][0]
    assert title == {"param_name": "title", "example": SAMPLES["search_alert.title"]}  # an example that fits


# --- Submitting to Meta ----------------------------------------------------------------------------------------


SNAPSHOT = Path(__file__).parent / "whatsapp_templates.json"


def _meta(name, body, status="APPROVED", category="UTILITY", language="en", id_="tpl-1") -> dict:
    return {"id": id_, "name": name, "language": language, "status": status, "category": category,
            "components": [{"type": "BODY", "text": body}]}


def test_sync_creates_edits_and_leaves_alone(graph):
    calls, answers = graph
    otp = {"id": "tpl-0", "name": "afe_sign_in_code", "language": "en", "status": "APPROVED",
           "category": "AUTHENTICATION", "components": [{"type": "BODY"}, {"type": "FOOTER", "code_expiration_minutes": 10}]}
    same = _meta("afe_viewing_confirmed", whatsapp_template("viewing_confirmed").body, id_="tpl-1")
    old = _meta("afe_new_message", "Afe: {{sender}} wrote about {{listing}}.", id_="tpl-2")
    other_language = _meta("afe_review_received", "Un locataire…", language="fr", id_="tpl-3")
    answers.append({"data": [otp, same], "paging": {"next": "https://graph.facebook.com/v21.0/next-page"}})
    answers.append({"data": [old, other_language]})
    results = {r["name"]: r for r in sync_all()}
    assert calls[0].get_method() == "GET" and "fields=id,name,language,status,category,components" in calls[0].full_url
    assert calls[1].full_url == "https://graph.facebook.com/v21.0/next-page"
    assert results["afe_sign_in_code"]["action"] == "unchanged"
    assert results["afe_viewing_confirmed"]["action"] == "unchanged"
    assert results["afe_new_message"]["action"] == "edited"
    edit = next(c for c in calls if c.full_url.endswith("/tpl-2"))
    assert json.loads(edit.data) == {"components": whatsapp_template("new_message").submission()["components"],
                                     "message_send_ttl_seconds": 3600}
    assert results["afe_review_received"]["action"] == "created"  # only the French one existed
    created = [json.loads(c.data)["name"] for c in calls if c.full_url.endswith("/waba-1/message_templates")]
    assert len(created) == len(registry()) - 3 and "afe_review_received" in created
    assert not any("error" in r for r in results.values())


def test_sync_reports_what_it_cannot_do(graph):
    _, answers = graph
    reviewing = _meta("afe_new_message", "Afe: {{sender}} wrote.", status="PENDING", id_="tpl-2")
    moved = _meta("afe_account_restored", whatsapp_template("account_restored").body, category="MARKETING", id_="tpl-4")
    answers.append({"data": [reviewing, moved]})
    results = {r["name"]: r for r in sync_all()}
    assert "while it's PENDING" in results["afe_new_message"]["error"]
    assert "filed it as MARKETING" in results["afe_account_restored"]["error"]


def test_sync_needs_the_business_account(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_business_account_id", "")
    with pytest.raises(providers.DeliveryError, match="AFE_WHATSAPP_BUSINESS_ACCOUNT_ID"):
        sync_all()


def test_each_template_says_how_long_meta_keeps_trying():
    assert whatsapp_template("otp").submission()["message_send_ttl_seconds"] == get_settings().otp_minutes * 60
    assert whatsapp_template("viewing_confirmed").submission()["message_send_ttl_seconds"] == 3600
    assert whatsapp_template("search_alert").submission()["message_send_ttl_seconds"] == 43200  # Meta's minimum


def test_whatsapp_wording_matches_the_snapshot():
    bodies = {wa.name: wa.body for wa in registry().values()}
    assert bodies == json.loads(SNAPSHOT.read_text(encoding="utf-8")), (
        "A WhatsApp template's wording changed. If you meant it, update the snapshot "
        "(python -m app.cli whatsapp-templates --bodies > tests/whatsapp_templates.json), then run "
        "python -m app.cli whatsapp-templates --submit so Meta reviews the new wording."
    )


def test_the_command_prints_the_bodies(capsys):
    assert main(["whatsapp-templates", "--bodies"]) == 0
    assert json.loads(capsys.readouterr().out) == {wa.name: wa.body for wa in registry().values()}


def test_the_command_prints_what_to_submit(capsys):
    assert main(["whatsapp-templates"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [t["name"] for t in printed] == [wa.name for wa in registry().values()]


# --- Sending ------------------------------------------------------------------------------------------------


class FlakyWhatsApp(providers.FakeWhatsApp):
    fails = 1

    def send_template(self, recipient, template, ctx):
        if FlakyWhatsApp.fails:
            FlakyWhatsApp.fails -= 1
            raise providers.DeliveryError("WhatsApp is unreachable: timed out")
        return super().send_template(recipient, template, ctx)


def test_notices_go_through_their_template_and_keep_its_parameters(db, landlord):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "review_received", rating=5)
    wa = next(n for n in notes if n.channel == "whatsapp")
    assert wa.status == "sent" and wa.data == {"rating": 5}
    assert fake_outbox.last("whatsapp", landlord.phone).body == "A tenant left you a 5-star review on Afe."


def test_replies_go_as_free_text_and_keep_no_parameters(db):
    note = send_direct(db, "whatsapp", "+233551112222", "check_reply", text="Line one\nLine two")
    assert note.status == "sent" and note.data == {}
    assert fake_outbox.last("whatsapp", "+233551112222").body == "Line one\nLine two"


def test_sign_in_codes_on_whatsapp_keep_no_parameters(db):
    note = send_direct(db, "whatsapp", "+233551112222", "otp", code="123456")
    assert note.status == "sent" and note.data == {} and "123456" not in note.body
    assert "123456 is your verification code" in fake_outbox.last("whatsapp", "+233551112222").body


def test_an_event_without_a_whatsapp_template_is_not_sent_on_whatsapp(db):
    note = send_direct(db, "whatsapp", "+233551112222", "staff_invite", name="Esi", url="https://afe.example")
    assert note.status == "failed" and "No WhatsApp template for staff_invite" in note.error


def test_a_row_without_its_parameters_fails_its_retry_and_says_why(db, landlord):
    landlord.whatsapp_opt_in = True
    # A WhatsApp row written before rows kept their parameters.
    note = Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, template="review_received",
                        body="A tenant left you a 5-star review on Afe.", status="failed", attempts=1,
                        created_at=utcnow() - timedelta(minutes=6))
    db.add(note)
    db.flush()
    retry_failed(db)
    assert note.status == "failed" and "needs rating" in note.error


def test_a_failed_whatsapp_notice_is_retried_from_its_parameters(db, monkeypatch, landlord):
    landlord.whatsapp_opt_in = True
    monkeypatch.setattr(service, "provider_for", lambda channel: FlakyWhatsApp())
    FlakyWhatsApp.fails = 1
    [note] = notify_on(db, landlord, "tenancy_refunded", {"whatsapp"}, amount="GH₵ 10.00")
    assert note.status == "failed" and note.attempts == 1
    note.created_at -= timedelta(minutes=6)
    assert retry_failed(db)["sent"] == 1 and note.status == "sent"
    assert fake_outbox.last("whatsapp", landlord.phone).body == "Afe refunded GH₵ 10.00 to you."


# --- WhatsApp first -----------------------------------------------------------------------------------------


class DeadWhatsApp(providers.FakeWhatsApp):
    def send_template(self, recipient, template, ctx):
        raise providers.DeliveryError("WhatsApp refused the message (400): 131026")


@pytest.fixture
def dead_whatsapp(monkeypatch):
    real = service.provider_for
    monkeypatch.setattr(service, "provider_for", lambda channel: DeadWhatsApp() if channel == "whatsapp" else real(channel))


def test_people_who_opted_in_get_whatsapp_instead_of_sms(db, landlord):
    assert [n.channel for n in notify(db, landlord, "review_received", rating=5)] == ["in_app", "sms"]
    landlord.whatsapp_opt_in = True
    assert [n.channel for n in notify(db, landlord, "review_received", rating=5)] == ["in_app", "whatsapp"]


def test_money_events_go_by_both(db, landlord):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "tenancy_refunded", amount="GH₵ 10.00")
    assert [n.channel for n in notes] == ["in_app", "sms", "whatsapp"]


def test_events_with_no_whatsapp_template_still_go_by_sms(db, landlord):
    landlord.whatsapp_opt_in = True
    assert [n.channel for n in notify(db, landlord, "tenancy_review_invite", landlord="Ama")] == ["in_app", "sms"]


def test_a_text_message_asked_for_by_sms_goes_on_whatsapp_to_people_who_opted_in(db, landlord):
    landlord.whatsapp_opt_in = True
    notes = notify_on(db, landlord, "rent_due", {"in_app", "sms"}, tenant="Yaa", amount="GH₵ 10.00", when="1 Oct")
    assert [n.channel for n in notes] == ["in_app", "whatsapp"]
    # An alert follows the channel the person chose for it.
    alert = dict(title="2 bed", rent="GH₵ 10.00", area="East Legon", url="https://afe.example/homes/AFE-1")
    assert [n.channel for n in notify_on(db, landlord, "search_alert", {"sms"}, **alert)] == ["sms"]


def test_when_whatsapp_fails_the_notice_goes_by_sms_once(db, landlord, dead_whatsapp):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "review_received", rating=5)
    assert [n.channel for n in notes] == ["in_app", "whatsapp", "sms"]
    wa, sms = notes[1], notes[2]
    assert wa.status == "failed" and wa.attempts == MAX_ATTEMPTS  # WhatsApp isn't tried again
    assert sms.fallback_of_id == wa.id and sms.status == "sent"
    assert fake_outbox.last("sms", landlord.phone).body == "A tenant left you a 5-star review on Afe."
    wa.created_at -= timedelta(hours=1)
    assert retry_failed(db) == {"sent": 0, "failed": 0, "waiting": 0}


def test_no_fallback_for_money_events_or_alerts(db, landlord, dead_whatsapp):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "tenancy_refunded", amount="GH₵ 10.00")
    assert [n.channel for n in notes] == ["in_app", "sms", "whatsapp"]  # the SMS it gets anyway, no second one
    alert = dict(title="2 bed", rent="GH₵ 10.00", area="East Legon", url="https://afe.example/homes/AFE-1")
    assert [n.channel for n in notify_on(db, landlord, "search_alert", {"whatsapp"}, **alert)] == ["whatsapp"]


# --- Delivery reports ----------------------------------------------------------------------------------------


def _report(ref, status, **extra) -> dict:
    report = {"id": ref, "status": status, "timestamp": "1790000000", "recipient_id": "233244123456", **extra}
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": {"statuses": [report]}}]}]}


def _whatsapp_notice(db, landlord) -> Notification:
    landlord.whatsapp_opt_in = True
    return next(n for n in notify(db, landlord, "review_received", rating=5) if n.channel == "whatsapp")


def test_delivery_reports_only_move_a_message_forward(client, db, landlord):
    wa = _whatsapp_notice(db, landlord)
    db.commit()
    assert client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "read")).status_code == 200
    assert wa.status == "read" and wa.delivered_at == datetime.fromtimestamp(1790000000, UTC)
    client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "delivered"))  # late
    assert wa.status == "read"
    client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "failed"))  # after it was read
    assert wa.status == "read"
    assert client.post("/api/v1/webhooks/whatsapp", json=_report("wamid.not-ours", "delivered")).status_code == 200


def test_a_failure_report_sends_the_notice_by_sms_once(client, db, landlord):
    wa = _whatsapp_notice(db, landlord)
    db.commit()
    failed = _report(wa.provider_ref, "failed", errors=[{"code": 131026, "title": "Message undeliverable"}])
    client.post("/api/v1/webhooks/whatsapp", json=failed)
    client.post("/api/v1/webhooks/whatsapp", json=failed)  # Meta sends it again
    assert wa.status == "failed" and wa.error == "131026: Message undeliverable" and wa.attempts == MAX_ATTEMPTS
    fallbacks = select(func.count()).select_from(Notification).where(Notification.fallback_of_id == wa.id)
    assert db.scalar(fallbacks) == 1
    assert fake_outbox.last("sms", landlord.phone).body == "A tenant left you a 5-star review on Afe."


def test_a_report_with_no_timestamp_still_counts(db, landlord):
    wa = _whatsapp_notice(db, landlord)
    assert apply_whatsapp_status(db, {"id": wa.provider_ref, "status": "delivered"}) is wa
    assert wa.status == "delivered" and wa.delivered_at is not None
    assert apply_whatsapp_status(db, {"status": "delivered"}) is None


# --- The opt-in record -----------------------------------------------------------------------------------------


def _inbound(text, sender="233240000009") -> dict:
    return {"entry": [{"changes": [{"value": {"messages": [{"from": sender, "type": "text", "text": {"body": text}}]}}]}]}


def test_opting_in_and_out_is_recorded(client, db):
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    db.commit()
    h = api_login(client, "yaa")
    assert client.patch("/api/v1/me", headers=h, json={"whatsapp_opt_in": True}).status_code == 200
    assert renter.whatsapp_opt_in and renter.whatsapp_opt_in_source == "settings" and renter.whatsapp_opt_in_at
    client.patch("/api/v1/me", headers=h, json={"whatsapp_opt_in": True})  # no change, nothing new recorded
    client.post("/api/v1/webhooks/whatsapp", json=_inbound("STOP"))
    assert not renter.whatsapp_opt_in and renter.whatsapp_opt_out_at
    events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("account.whatsapp%")).order_by(AuditEvent.id))
    assert [(e.action, e.data["source"]) for e in events] == [
        ("account.whatsapp_opt_in", "settings"), ("account.whatsapp_opt_out", "whatsapp_stop"),
    ]
    account = client.get("/api/v1/me/export", headers=h).json()["account"]
    assert account["whatsapp_updates"] is False and account["whatsapp_opt_in_source"] == "settings"
    assert account["whatsapp_opted_in_at"] and account["whatsapp_opted_out_at"]


def test_asking_for_whatsapp_alerts_records_the_opt_in(db, area):
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    alerts.save_search(db, renter, alerts.parse_query(db, "2 bed east legon"), "whatsapp")
    assert renter.whatsapp_opt_in and renter.whatsapp_opt_in_source == "alert"


# --- Alarms ---------------------------------------------------------------------------------------------------------


def _quality(event) -> dict:
    value = {"display_phone_number": "233300000000", "event": event, "current_limit": "TIER_1K"}
    return {"entry": [{"changes": [{"field": "phone_number_quality_update", "value": value}]}]}


def test_a_quality_warning_reaches_the_admins(client, db):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    db.commit()
    assert client.post("/api/v1/webhooks/whatsapp", json=_quality("UPGRADE")).status_code == 200
    assert fake_outbox.last("sms", boss.phone) is None
    client.post("/api/v1/webhooks/whatsapp", json=_quality("FLAGGED"))
    assert "flagged" in fake_outbox.last("sms", boss.phone).body
    assert not [m for m in fake_outbox.messages if m.channel == "whatsapp"]  # never about WhatsApp on WhatsApp


def test_the_daily_check_finds_templates_that_keep_failing(db, landlord):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    for i in range(10):
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="viewing_confirmed", status="failed" if i < 3 else "delivered"))
    for _ in range(2):  # too few failures to judge
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="new_message", status="failed"))
    db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                        template="viewing_confirmed", status="failed", created_at=utcnow() - timedelta(days=2)))
    db.flush()
    assert whatsapp_health(db) == {"templates": 2, "failing": ["viewing_confirmed"], "no_reports": False}
    assert "viewing_confirmed: 3 of 10 failed" in fake_outbox.last("sms", boss.phone).body


# --- Review fixes ---------------------------------------------------------------------------------------------


def test_delivery_reports_find_their_message_by_an_index():
    indexed = {tuple(c.name for c in ix.columns) for ix in Notification.__table__.indexes}
    assert ("provider_ref",) in indexed


def test_a_code_whatsapp_accepted_but_could_not_deliver_goes_again_by_sms(client, db):
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    db.commit()
    ask = {"phone": renter.phone, "purpose": "login", "channel": "whatsapp"}
    assert client.post("/api/v1/auth/code", json=ask).status_code == 202
    wa = db.scalar(select(Notification).where(Notification.template == "otp", Notification.channel == "whatsapp"))
    failed = _report(wa.provider_ref, "failed", errors=[{"code": 131026, "title": "Message undeliverable"}])
    client.post("/api/v1/webhooks/whatsapp", json=failed)
    code = re.search(r"\b(\d{6})\b", fake_outbox.last("sms", renter.phone).body).group(1)
    signed_in = client.post("/api/v1/auth/signin/code", json={"phone": renter.phone, "code": code})
    assert signed_in.json()["data"]["status"] == "signed_in"
    stored = db.scalar(select(Notification).where(Notification.template == "otp", Notification.channel == "sms"))
    assert "******" in stored.body and code not in stored.body


def test_people_who_opted_out_get_no_whatsapp_alerts_or_retries(db, monkeypatch, landlord):
    alert = dict(title="2 bed", rent="GH₵ 10.00", area="East Legon", url="https://afe.example/homes/AFE-1")
    assert [n.channel for n in notify_on(db, landlord, "search_alert", {"whatsapp", "in_app"}, **alert)] == ["in_app"]
    landlord.whatsapp_opt_in = True
    monkeypatch.setattr(service, "provider_for", lambda channel: FlakyWhatsApp())
    FlakyWhatsApp.fails = 1
    [note] = notify_on(db, landlord, "search_alert", {"whatsapp"}, **alert)
    assert note.status == "failed"
    set_whatsapp_opt_in(db, landlord, False, "settings")
    note.created_at -= timedelta(minutes=6)
    assert retry_failed(db) == {"sent": 0, "failed": 0, "waiting": 0} and note.status == "failed"


# --- Messages that never arrive -------------------------------------------------------------------------------


def _delivered_recently(db, landlord):
    ok = _whatsapp_notice(db, landlord)
    apply_whatsapp_status(db, {"id": ok.provider_ref, "status": "delivered"})


def test_a_failure_reported_hours_late_sends_no_sms(db, landlord):
    wa = _whatsapp_notice(db, landlord)
    wa.created_at -= timedelta(hours=7)
    apply_whatsapp_status(db, {"id": wa.provider_ref, "status": "failed", "errors": [{"code": 131026}]})
    assert wa.status == "failed"
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.fallback_of_id == wa.id)) == 0


def test_a_message_with_no_report_after_its_time_to_live_goes_by_sms(db, landlord):
    _delivered_recently(db, landlord)
    late = _whatsapp_notice(db, landlord)
    fresh = _whatsapp_notice(db, landlord)
    late.created_at -= timedelta(hours=1, minutes=11)
    assert expire_undelivered(db) == {"expired": 1, "reporting": True}
    assert late.status == "failed" and "time-to-live" in late.error and fresh.status == "sent"
    sms = db.scalar(select(Notification).where(Notification.fallback_of_id == late.id))
    assert sms.channel == "sms" and sms.status == "sent"


def test_no_sweep_while_no_delivery_reports_arrive(db, landlord):
    wa = _whatsapp_notice(db, landlord)
    wa.created_at -= timedelta(hours=2)
    assert expire_undelivered(db) == {"expired": 0, "reporting": False}
    assert wa.status == "sent"


# --- Template alarms ------------------------------------------------------------------------------------------


def _template_event(field, value) -> dict:
    return {"entry": [{"changes": [{"field": field, "value": value}]}]}


def test_meta_template_problems_reach_the_admins(client, db):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    db.commit()
    approved = {"event": "APPROVED", "message_template_name": "afe_new_message", "reason": "NONE"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("message_template_status_update", approved))
    assert fake_outbox.last("sms", boss.phone) is None
    rejected = {"event": "REJECTED", "message_template_name": "afe_new_message", "reason": "INVALID_FORMAT"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("message_template_status_update", rejected))
    assert "afe_new_message" in fake_outbox.last("sms", boss.phone).body
    assert "rejected (INVALID_FORMAT)" in fake_outbox.last("sms", boss.phone).body
    fake_outbox.clear()
    same = {"message_template_name": "afe_search_alert", "new_category": "MARKETING"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("template_category_update", same))
    assert fake_outbox.last("sms", boss.phone) is None  # already marketing
    moving = {"message_template_name": "afe_viewing_confirmed", "new_category": "UTILITY", "correct_category": "MARKETING"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("template_category_update", moving))
    assert "moved to marketing" in fake_outbox.last("sms", boss.phone).body


def test_the_daily_check_notices_when_no_delivery_reports_arrive(db, landlord):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    for i in range(10):
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="viewing_confirmed", status="sent", provider_ref=f"wamid.{i}",
                            created_at=utcnow() - timedelta(hours=3)))
    db.flush()
    assert whatsapp_health(db) == {"templates": 1, "failing": [], "no_reports": True}
    assert "no delivery reports" in fake_outbox.last("sms", boss.phone).body


def test_help_leaves_out_moved_in_while_protected_payments_are_off(client):
    client.post("/api/v1/webhooks/whatsapp", json=_inbound("hello", sender="233551112222"))
    assert "MOVED IN" not in fake_outbox.last("whatsapp", "+233551112222").body


# --- Review fixes ---------------------------------------------------------------------------------------------


def test_sync_sets_the_time_to_live_on_a_template_meta_already_has(graph):
    _, answers = graph
    long_lived = _meta("afe_viewing_confirmed", whatsapp_template("viewing_confirmed").body, id_="tpl-1")
    long_lived["message_send_ttl_seconds"] = 2592000
    answers.append({"data": [long_lived]})
    results = {r["name"]: r for r in sync_all()}
    assert results["afe_viewing_confirmed"]["action"] == "edited"


def test_a_late_failure_never_replaces_a_newer_code(client, db):
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    db.commit()
    client.post("/api/v1/auth/code", json={"phone": renter.phone, "purpose": "login", "channel": "whatsapp"})
    wa = db.scalar(select(Notification).where(Notification.template == "otp", Notification.channel == "whatsapp"))
    client.post("/api/v1/auth/code", json={"phone": renter.phone, "purpose": "login", "channel": "sms"})
    newer = re.search(r"\b(\d{6})\b", fake_outbox.last("sms", renter.phone).body).group(1)
    client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "failed", errors=[{"code": 131026}]))
    assert [m.channel for m in fake_outbox.messages].count("sms") == 1  # no third code
    signed_in = client.post("/api/v1/auth/signin/code", json={"phone": renter.phone, "code": newer})
    assert signed_in.json()["data"]["status"] == "signed_in"


def test_no_sweep_once_reports_stopped_before_a_message_was_due(db, landlord):
    ok = _whatsapp_notice(db, landlord)
    twenty_hours_ago = str(int((utcnow() - timedelta(hours=20)).timestamp()))
    apply_whatsapp_status(db, {"id": ok.provider_ref, "status": "delivered", "timestamp": twenty_hours_ago})
    wa = _whatsapp_notice(db, landlord)
    wa.created_at -= timedelta(hours=2)
    assert expire_undelivered(db)["expired"] == 0 and wa.status == "sent"


def test_the_daily_check_notices_when_reports_stop_part_way(db, landlord):
    make_user(db, "boss", Role.ADMIN, phone="0200000001")
    db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                        template="viewing_confirmed", status="delivered", provider_ref="wamid.r",
                        created_at=utcnow() - timedelta(hours=20), delivered_at=utcnow() - timedelta(hours=20)))
    for i in range(10):
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="viewing_confirmed", status="sent", provider_ref=f"wamid.{i}",
                            created_at=utcnow() - timedelta(hours=3)))
    db.flush()
    assert whatsapp_health(db)["no_reports"] is True


def test_messages_the_sweep_gave_up_on_are_not_template_failures(db, landlord):
    _delivered_recently(db, landlord)
    late = [_whatsapp_notice(db, landlord) for _ in range(3)]
    for note in late:
        note.created_at -= timedelta(hours=1, minutes=11)
    assert expire_undelivered(db)["expired"] == 3
    assert whatsapp_health(db)["failing"] == []
    apply_whatsapp_status(db, {"id": late[0].provider_ref, "status": "delivered"})  # it arrived after all
    assert late[0].status == "delivered" and late[0].delivered_at is not None
