"""The verification fee, the payment webhook, and WhatsApp "Check before you pay"."""

import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import RuleViolation
from app.modules.audit.models import WebhookReceipt
from app.modules.billing import service as billing
from app.modules.billing.models import PaymentStatus
from app.modules.billing.providers import PaymentError, Paystack, WebhookEvent
from app.modules.notifications.providers import fake_outbox
from app.modules.verification.service import assign_visit, homes_awaiting_fee, homes_needing_visit
from tests.conftest import PDF, api_login, make_listing


@pytest.fixture
def fee(monkeypatch, charges_on):
    monkeypatch.setattr(get_settings(), "verification_fee_pesewas", 20_000)  # GH₵200


@pytest.fixture
def home_with_documents(db, unit, landlord):
    from app.modules.units.models import DocumentType, Relationship
    from app.modules.units.service import add_authority

    add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.INDENTURE, PDF)
    return unit


def test_no_fee_means_nothing_to_pay(db, home_with_documents):
    assert billing.fee_settled(db, home_with_documents)
    assert homes_awaiting_fee(db) == []


def test_fee_must_be_paid_before_a_visit(db, fee, home_with_documents, landlord, verifier, reviewer):
    assert homes_awaiting_fee(db) == [home_with_documents] and homes_needing_visit(db) == []
    with pytest.raises(RuleViolation, match="fee"):
        assign_visit(db, home_with_documents, verifier, reviewer, home_with_documents.created_at.date())

    payment = billing.start_verification_fee(db, landlord, home_with_documents)
    assert payment.status == PaymentStatus.PENDING and payment.checkout_url.endswith(f"/pay/test/{payment.reference}")
    event = WebhookEvent(payment.reference, True, 20_000, "GHS", {})
    billing.apply_webhook(db, event)
    billing.apply_webhook(db, event)  # partners resend; the second is harmless
    assert payment.status == PaymentStatus.PAID
    assert "Receipt" in fake_outbox.last("sms", landlord.phone).body
    assert homes_needing_visit(db) == [home_with_documents]
    with pytest.raises(RuleViolation, match="already settled"):
        billing.start_verification_fee(db, landlord, home_with_documents)


def test_wrong_amount_is_not_accepted(db, fee, home_with_documents, landlord):
    payment = billing.start_verification_fee(db, landlord, home_with_documents)
    billing.apply_webhook(db, WebhookEvent(payment.reference, True, 100, "GHS", {}))
    assert payment.status == PaymentStatus.FAILED and "mismatch" in payment.note


def test_reviewers_can_waive_the_fee(db, fee, home_with_documents, reviewer, landlord):
    with pytest.raises(RuleViolation, match="why"):
        billing.waive_fee(db, home_with_documents, reviewer, "")
    billing.waive_fee(db, home_with_documents, reviewer, "Founding landlord")
    assert billing.fee_settled(db, home_with_documents)


def test_paystack_webhook_signature(monkeypatch):
    monkeypatch.setattr(get_settings(), "paystack_secret_key", "sk_test_123")
    body = json.dumps(
        {
            "event": "charge.success",
            "data": {"reference": "AFE-VF-1-AB", "status": "success", "amount": 20000, "currency": "GHS"},
        }
    ).encode()
    good = hmac.new(b"sk_test_123", body, hashlib.sha512).hexdigest()
    event = Paystack().parse_webhook(body, {"x-paystack-signature": good})
    assert event.reference == "AFE-VF-1-AB" and event.paid and event.amount_pesewas == 20000
    with pytest.raises(PaymentError):
        Paystack().parse_webhook(body, {"x-paystack-signature": "forged"})


def test_fee_over_the_api(client, db, fee, home_with_documents):
    db.commit()
    ama = api_login(client, "ama")
    home = client.get(f"/api/v1/properties/units/{home_with_documents.id}", headers=ama).json()["data"]
    assert home["stage"] == "fee" and home["fee_required"] and not home["fee_settled"]
    payment = client.post(
        "/api/v1/payments/verification-fee", headers=ama, json={"unit_id": home_with_documents.id}
    ).json()["data"]
    assert payment["amount_display"] == "GH₵200"
    invoice = client.get(f"/api/v1/payments/{payment['reference']}/document", headers=ama)
    assert invoice.status_code == 200 and b"(INVOICE)" in invoice.content and b"(AWAITING PAYMENT)" in invoice.content
    assert b"(GHS 200.00)" in invoice.content
    done = client.post(f"/api/v1/payments/test/{payment['reference']}/complete", headers=ama).json()["data"]
    assert done["status"] == "paid"
    home = client.get(f"/api/v1/properties/units/{home_with_documents.id}", headers=ama).json()["data"]
    assert home["stage"] == "visit"
    receipt = client.get(f"/api/v1/payments/{payment['reference']}/document", headers=ama)
    assert b"(RECEIPT)" in receipt.content and b"(PAID)" in receipt.content
    paid = client.get("/api/v1/me/payments", headers=ama).json()["data"]
    assert [(p["reference"], p["status"], p["purpose"]) for p in paid] == [(payment["reference"], "paid", "verification_fee")]
    assert paid[0]["subject"].startswith(home_with_documents.digital_address)


def test_landlord_dashboard_stages(client, db, verified_unit, verified_landlord):
    make_listing(db, verified_unit, verified_landlord)
    db.commit()
    units = client.get("/api/v1/me/units", headers=api_login(client, "ama")).json()["data"]
    assert [u["stage"] for u in units] == ["verified"] and len(units[0]["listings"]) == 1


# --- WhatsApp ---------------------------------------------------------------------------------


def _whatsapp(text: str, sender="233551112222") -> dict:
    return {
        "entry": [{"changes": [{"value": {"messages": [{"from": sender, "type": "text", "text": {"body": text}}]}}]}]
    }


def test_whatsapp_check_before_you_pay(client, db, monkeypatch, verified_landlord):
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "app-secret")
    db.commit()
    body = json.dumps(_whatsapp("024 412 3456")).encode()
    signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    res = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={"x-hub-signature-256": signature, "content-type": "application/json"},
    )
    assert res.status_code == 200
    reply = fake_outbox.last("whatsapp", "+233551112222").body
    assert "verified by Afe" in reply and "Never pay before" in reply

    forged = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={"x-hub-signature-256": "sha256=0", "content-type": "application/json"},
    )
    assert forged.status_code == 403


def test_whatsapp_report_and_help(client, db):
    client.post("/api/v1/webhooks/whatsapp", json=_whatsapp("REPORT he asked me for a viewing fee on momo"))
    assert "Thank you" in fake_outbox.last("whatsapp", "+233551112222").body
    client.post("/api/v1/webhooks/whatsapp", json=_whatsapp("hello"))
    assert "a phone number or listing reference" in fake_outbox.last("whatsapp", "+233551112222").body


def test_whatsapp_subscription_check(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "tok")
    ok = client.get(
        "/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "42"}
    )
    assert ok.text == "42"
    assert (
        client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x"}).status_code
        == 403
    )


def test_analytics_events(client, db):
    assert client.post("/api/v1/events", json={"name": "search", "props": {"area": "east-legon"}}).status_code == 202
    assert client.post("/api/v1/events", json={"name": "made_up"}).status_code == 422


def test_every_fee_webhook_is_kept_as_evidence(client, db, monkeypatch):
    assert client.post("/api/v1/payments/webhook", content=b'{"reference": "AFE-P-NONE", "amount": 100}').status_code == 200
    bad = client.post("/api/v1/payments/webhook", content=b"not json")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_input"
    monkeypatch.setattr(get_settings(), "payment_provider", "app.modules.billing.providers.Paystack")
    monkeypatch.setattr(get_settings(), "paystack_secret_key", "sk_test")
    forged = client.post("/api/v1/payments/webhook", content=b'{"event": "charge.success"}',
                         headers={"x-paystack-signature": "0" * 128})
    assert forged.status_code == 422
    receipts = list(db.scalars(select(WebhookReceipt).order_by(WebhookReceipt.id)))
    assert [(r.source, r.endpoint, r.outcome) for r in receipts] == [
        ("fake", "fees", "unmatched"), ("fake", "fees", "rejected"), ("paystack", "fees", "rejected")]
    assert receipts[1].body == "not json" and "signature" in receipts[2].error
    assert receipts[2].headers["x-paystack-signature"] == "0" * 128
    receipts[0].outcome = "applied"
    with pytest.raises(PermissionError):
        db.flush()  # evidence can't be changed


def test_unverified_webhooks_keep_only_a_fingerprint_and_are_rate_limited(client, db):
    junk = b"x" * 10_000
    for _ in range(61):
        assert client.post("/api/v1/payments/webhook", content=junk).status_code == 422
    receipts = list(db.scalars(select(WebhookReceipt)))
    assert len(receipts) == 60  # one address can't fill the table
    assert len(receipts[0].body) == 2048 and receipts[0].size == 10_000
    assert receipts[0].sha256 == hashlib.sha256(junk).hexdigest()
