"""Strengthening Phases 1-3: malware scanning, public rate limits, device links, payment
receipts and unannounced verifier re-checks."""

import dataclasses
import socket
import struct
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import InvalidInput, UploadRejected
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.compliance import service as compliance
from app.modules.detection.models import LinkEdge
from app.modules.detection.service import run_graph
from app.modules.enquiries import service as enquiries
from app.modules.listings.service import publish, submit_for_review
from app.modules.media import scan
from app.modules.notifications.providers import fake_outbox
from app.modules.risk.flags import open_flags
from app.modules.units.models import DocumentType, Relationship
from app.modules.units.service import add_authority
from app.modules.verification.models import VisitAssignment
from app.modules.verification.service import complete_visit, decide_unit, start_visit, verifier_stats
from tests.conftest import PDF, api_login, make_listing, make_user

# --- Malware scanning --------------------------------------------------------------------------------


def test_infected_document_is_refused_and_flagged(db, unit, landlord):
    with pytest.raises(UploadRejected, match="virus check"):
        add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.INDENTURE, b"%PDF-1.4\n" + scan.EICAR)
    assert [f.rule for f in open_flags(db, landlord)] == ["upload.malware"]
    assert unit.authority_records == []


def test_scanner_down_means_no_upload(db, monkeypatch, unit, landlord):
    class Down:
        def scan(self, data):
            raise scan.ScanUnavailable("connection refused")

    monkeypatch.setattr(scan, "get_scanner", lambda: Down())
    with pytest.raises(InvalidInput, match="couldn't check this file"):
        add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.INDENTURE, PDF)


def test_malware_flag_survives_the_refused_request(client, db, unit, landlord):
    h = api_login(client, "ama")
    files = {"document": ("deed.pdf", b"%PDF-1.4\n" + scan.EICAR, "application/pdf")}
    res = client.post(f"/api/v1/kyc/units/{unit.id}/authority", headers=h, files=files,
                      data={"relationship": "owner", "document_type": "indenture"})
    assert res.status_code == 422 and "virus check" in res.json()["error"]["message"]
    db.expire_all()
    assert "upload.malware" in [f.rule for f in open_flags(db, landlord)]


@pytest.fixture
def fake_clamd(monkeypatch):
    """A tiny clamd speaking INSTREAM, to test the real scanner's protocol."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]

    def serve():
        for _ in range(2):
            conn, _ = server.accept()
            with conn:
                data = b""
                while not data.startswith(b"zINSTREAM\0"):
                    data += conn.recv(4096)
                data = data[len(b"zINSTREAM\0"):]
                body = b""
                while True:
                    while len(data) < 4:
                        data += conn.recv(4096)
                    size = struct.unpack("!L", data[:4])[0]
                    data = data[4:]
                    if size == 0:
                        break
                    while len(data) < size:
                        data += conn.recv(65536)
                    body, data = body + data[:size], data[size:]
                reply = b"stream: Eicar-Signature FOUND\0" if scan.EICAR in body else b"stream: OK\0"
                conn.sendall(reply)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    monkeypatch.setattr(get_settings(), "clamd_host", "127.0.0.1")
    monkeypatch.setattr(get_settings(), "clamd_port", port)
    yield
    server.close()


def test_clamav_protocol(fake_clamd):
    scanner = scan.ClamAvScanner()
    assert scanner.scan(PDF * 50_000).clean  # several chunks
    result = scanner.scan(b"%PDF-1.4\n" + scan.EICAR)
    assert not result.clean and result.signature == "Eicar-Signature"


def test_production_refuses_the_fake_scanner():
    from app.config import Settings

    with pytest.raises(ValueError, match="AFE_MALWARE_SCANNER"):
        Settings(debug=False, secret_key="x" * 40, storage_backend="s3",
                 database_url="postgresql+psycopg://a:b@db/afe",
                 kyc_provider="x.Real", sms_provider="x.Real", whatsapp_provider="x.Real",
                 email_provider="x.Real", payment_provider="x.Real")


# --- Rate limits on public endpoints ----------------------------------------------------------------------


def test_check_and_report_are_rate_limited(client):
    for _ in range(60):
        assert client.get("/api/v1/check", params={"q": "0244000000"}).status_code == 200
    assert client.get("/api/v1/check", params={"q": "0244000000"}).status_code == 429
    body = {"what_happened": "Asked for a viewing fee before showing me anything"}
    for _ in range(5):
        assert client.post("/api/v1/check/reports", json=body).status_code == 201
    assert client.post("/api/v1/check/reports", json=body).status_code == 429


def test_one_whatsapp_sender_cannot_run_up_the_bill(client):
    def message(i):
        return {"entry": [{"changes": [{"value": {"messages": [
            {"type": "text", "from": "233551112222", "text": {"body": f"024400000{i % 10}"}}]}}]}]}

    for i in range(35):
        assert client.post("/api/v1/webhooks/whatsapp", json=message(i)).status_code == 200
    replies = [m for m in fake_outbox.messages if m.channel == "whatsapp" and m.recipient == "+233551112222"]
    assert len(replies) == 30


# --- Device links --------------------------------------------------------------------------------------------


def test_accounts_signed_in_on_one_device_are_linked(client, db, landlord, reviewer):
    other = make_user(db, "kojo", Role.AGENT)
    db.flush()
    device = {"X-Afe-Device-Id": "3f6c2a9e-1d4b-4c8e-9a7f-2b5d8e1c4a60"}
    for username in ("ama", "kojo", "reviewer"):
        res = client.post("/api/v1/auth/signin/password", headers=device,
                          json={"login": username, "password": "x-test-password"})
        assert res.status_code == 200
    run_graph(db)
    edges = db.scalars(select(LinkEdge).where(LinkEdge.kind == "device")).all()
    assert [(e.user_a_id, e.user_b_id) for e in edges] == [tuple(sorted((landlord.id, other.id)))]  # staff excluded
    assert "3f6c2a9e" in edges[0].evidence


def test_malformed_device_ids_are_ignored(client, db, landlord):
    from app.modules.accounts.models import RefreshToken

    client.post("/api/v1/auth/signin/password", headers={"X-Afe-Device-Id": "<script>"},
                json={"login": "ama", "password": "x-test-password"})
    assert db.scalar(select(RefreshToken.device_id)) == ""


# --- Receipts ------------------------------------------------------------------------------------------------


def test_receipts_for_tenant_and_landlord(client, db, monkeypatch, verified_unit, verified_landlord, reviewer):
    from app.modules.tenancies import service as tenancies
    from app.modules.tenancies.partners import PartnerEvent, TestEscrow

    monkeypatch.setattr(get_settings(), "protected_payments_enabled", True)
    TestEscrow.register_name("0244123456", "AMA")
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    publish(db, listing, reviewer)
    viewing = enquiries.request_viewing(db, renter, listing, utcnow() + timedelta(days=1))
    enquiries.respond_viewing(db, viewing, verified_landlord, True)
    viewing.requested_for = utcnow() - timedelta(hours=2)
    enquiries.complete_viewing(db, viewing, verified_landlord, attended=True)
    tenancies.set_payee(db, verified_landlord, "momo_mtn", "0244123456", "")
    t = tenancies.make_offer(db, verified_landlord, viewing, utcnow().date() + timedelta(days=7), 12, 6, 0)
    tenancies.accept(db, renter, t)
    db.commit()

    yaa = api_login(client, "yaa")
    assert client.get(f"/api/v1/tenancies/{t.reference}/receipt", headers=yaa).status_code == 404  # nothing paid yet
    ref = TestEscrow.record_charge(t.reference, t.charge_pesewas)
    tenancies.apply_partner_event(db, PartnerEvent("charge.succeeded", t.reference, t.charge_pesewas, ref))
    db.commit()
    res = client.get(f"/api/v1/tenancies/{t.reference}/receipt", headers=yaa)
    assert res.status_code == 200 and res.content.startswith(b"%PDF")
    assert client.get(f"/api/v1/tenancies/{t.reference}", headers=yaa).json()["data"]["has_receipt"]
    assert client.get(f"/api/v1/tenancies/{t.reference}/receipt", headers=api_login(client, "ama")).status_code == 404
    assert client.get(f"/api/v1/tenancies/{t.reference}/receipt", headers=api_login(client, "reviewer")).status_code == 404


# --- Verifier quality re-checks ------------------------------------------------------------------------------


@pytest.fixture
def every_approval_rechecked(monkeypatch):
    key = "qa_recheck_percent"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default=100))


def test_approval_schedules_an_unannounced_recheck_by_another_verifier(
    db, every_approval_rechecked, verified_unit, verifier
):
    checker_assignment = db.scalar(select(VisitAssignment).where(VisitAssignment.purpose == "qa_recheck"))
    assert checker_assignment is None  # only one verifier exists: nobody else can re-check
    other = make_user(db, "verifier2", Role.FIELD_VERIFIER)
    reviewer2 = make_user(db, "reviewer2", Role.REVIEWER)
    decide_unit(db, verified_unit, reviewer2, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    recheck = db.scalar(select(VisitAssignment).where(VisitAssignment.purpose == "qa_recheck"))
    assert recheck.verifier_id == other.id and recheck.rechecks_visit_id is not None
    assert "unannounced" in recheck.note


def test_failed_recheck_pauses_the_home_and_flags_the_verifier(db, every_approval_rechecked, unit, verified_landlord,
                                                                reviewer, verifier):
    from tests.conftest import accept_owner_authority, passed_visit

    other = make_user(db, "verifier2", Role.FIELD_VERIFIER)
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    passed_visit(db, unit, verifier)
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    recheck = db.scalar(select(VisitAssignment).where(VisitAssignment.purpose == "qa_recheck"))
    visit = start_visit(db, unit, other, unit.lat, unit.lng)
    complete_visit(db, visit, other, {"unit_exists": True, "unit_vacant": False}, notes="Occupied, different kitchen")
    assert recheck.status == "done"
    assert "qa.recheck_failed" in [f.rule for f in open_flags(db, unit)]
    assert "qa.verifier_reversal" in [f.rule for f in open_flags(db, verifier)]
    stats = {row["name"]: row for row in verifier_stats(db)}
    assert stats[verifier.name]["rechecked"] == 1 and stats[verifier.name]["reversals"] == 1


def test_pricing_says_what_is_free(client):
    data = client.get("/api/v1/pricing").json()["data"]
    assert data["launch_offer"] and data["free_until"] == "2027-06-05"
    assert data["protection_fee_bps"] == 0 and data["featured_fee_pesewas"] == 0


def test_pricing_after_the_launch_offer(client, charges_on):
    data = client.get("/api/v1/pricing").json()["data"]
    assert not data["launch_offer"] and data["protection_fee_bps"] == 350 and data["featured_fee_pesewas"] == 15_000


# --- Headers and unexpected errors ------------------------------------------------------------------------


def test_security_headers(client):
    res = client.get("/api/v1/check", params={"q": "0244000000"})
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["cross-origin-resource-policy"] == "same-site"
    # Public listing photos are shown by the website and the app, which are other origins.
    photo = client.get("/media/units/none.webp")
    assert photo.headers["cross-origin-resource-policy"] == "cross-origin"


def test_unexpected_errors_get_a_reference_not_details(db, monkeypatch, caplog):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import create_app
    from app.modules.scamcheck import service as scamcheck

    def boom(*_, **__):
        raise RuntimeError("secret detail +233244123456")

    monkeypatch.setattr(scamcheck, "check", boom)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/api/v1/check", params={"q": "0244000000"})
    body = res.json()
    assert res.status_code == 500 and body["error"]["code"] == "server_error"
    assert "Quote reference" in body["error"]["message"] and "233244123456" not in res.text
    assert "unhandled_error" in caplog.text
