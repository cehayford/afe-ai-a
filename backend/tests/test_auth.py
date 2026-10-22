"""Sign-up and sign-in: SMS codes, two-step sign-in, rotating refresh tokens, limits."""

import re

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core import totp
from app.modules.accounts.models import Role, User
from app.modules.notifications.models import Notification
from app.modules.notifications.providers import fake_outbox
from tests.conftest import PASSWORD, make_user

PHONE = "+233244000111"


def sms_code(phone=PHONE) -> str:
    message = fake_outbox.last("sms", phone)
    assert message is not None, "no SMS sent"
    return re.search(r"\b(\d{6})\b", message.body).group(1)


def signup(client, role="renter", name="Esi Owusu", phone=PHONE):
    assert client.post("/api/v1/auth/code", json={"phone": phone, "purpose": "signup"}).status_code == 202
    res = client.post(
        "/api/v1/auth/signup",
        json={"phone": phone, "code": sms_code(phone), "display_name": name, "role": role, "accept_privacy": True},
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


def test_totp_matches_rfc_6238():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
    assert totp.now_code(secret, at=59) == "287082"
    assert totp.verify(secret, "287082", at=59)
    assert totp.verify(secret, "287082", at=59 + 30)  # one step of clock drift
    assert not totp.verify(secret, "287082", at=59 + 90)
    assert not totp.verify(secret, "abc")


def test_renter_signs_up_with_an_sms_code(client, db):
    data = signup(client)
    assert data["status"] == "signed_in" and data["user"]["phone"] == PHONE
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {data['access_token']}"}).json()["data"]
    assert me["user"]["role"] == "renter" and me["verification"] is None

    # The stored copy of the SMS never contains the code.
    stored = db.scalar(select(Notification).where(Notification.template == "otp"))
    assert "******" in stored.body and not re.search(r"\d{6}", stored.body)


def test_codes_are_single_use_and_phone_numbers_stay_private(client, db):
    signup(client)
    # Signing up twice with the same number sends nothing and looks the same.
    fake_outbox.clear()
    res = client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "signup"})
    assert res.status_code == 202 and fake_outbox.messages == []
    # Asking to sign in with an unknown number also looks the same, and sends nothing.
    res = client.post("/api/v1/auth/code", json={"phone": "0551112222", "purpose": "login"})
    assert res.status_code == 202 and fake_outbox.messages == []

    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login"})
    code = sms_code()
    assert (
        client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": code}).json()["data"]["status"]
        == "signed_in"
    )
    again = client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": code})
    assert again.status_code == 401


def test_the_code_can_go_by_whatsapp_and_falls_back_to_sms(client, db, monkeypatch):
    signup(client)
    fake_outbox.clear()
    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login", "channel": "whatsapp"})
    assert [m.channel for m in fake_outbox.messages] == ["whatsapp"]
    code = re.search(r"\b(\d{6})\b", fake_outbox.last("whatsapp", PHONE).body).group(1)
    assert client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": code}).json()["data"]["status"] == "signed_in"

    # WhatsApp can't deliver: the same request still gets a code, by SMS.
    from app.modules.notifications import service as notifications

    real = notifications.provider_for
    monkeypatch.setattr(notifications, "provider_for", lambda channel: None if channel == "whatsapp" else real(channel))
    fake_outbox.clear()
    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login", "channel": "whatsapp"})
    assert [m.channel for m in fake_outbox.messages] == ["sms"]
    assert client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login", "channel": "fax"}).status_code == 422


def test_wrong_codes_count_even_though_the_request_fails(client, db):
    signup(client)
    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login"})
    code = sms_code()
    for _ in range(get_settings().otp_max_attempts):
        assert client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": "000000"}).status_code == 401
    locked = client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": code})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "too_many_attempts"


def test_password_attempts_are_limited(client, db):
    make_user(db, "efua", Role.REVIEWER)
    db.commit()
    for _ in range(get_settings().login_attempts_per_15_min):
        client.post("/api/v1/auth/signin/password", json={"login": "efua", "password": "wrong-password"})
    res = client.post("/api/v1/auth/signin/password", json={"login": "efua", "password": PASSWORD})
    assert res.status_code == 429


def test_code_requests_are_limited(client, db):
    for _ in range(get_settings().otp_per_phone_per_hour):
        client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "signup"})
    assert client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "signup"}).status_code == 429


def test_refresh_tokens_rotate_and_reuse_ends_the_session(client, db):
    first = signup(client)
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()["data"]
    assert second["status"] == "signed_in" and second["refresh_token"] != first["refresh_token"]

    # Two tabs refreshing at the same moment is fine...
    race = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert race.status_code == 200

    # ...but replaying the old token later (e.g. a stolen copy) revokes the whole family.
    from datetime import timedelta

    from app.modules.accounts.models import RefreshToken

    for row in db.scalars(select(RefreshToken)):
        if row.used_at:
            row.used_at -= timedelta(minutes=5)
    db.commit()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_sign_out_and_devices(client, db):
    a = signup(client)
    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login"})
    b = client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": sms_code()}).json()["data"]
    headers = {"Authorization": f"Bearer {b['access_token']}"}
    assert len(client.get("/api/v1/me/devices", headers=headers).json()["data"]) == 2

    client.post("/api/v1/auth/signout", json={"refresh_token": a["refresh_token"]})
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": a["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/signout/everywhere", headers=headers).json()["data"]["devices"] == 1
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 401


def test_landlords_and_staff_need_an_authenticator(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_enforced", True)
    setup = signup(client, role="landlord", name="Ama Owusu")
    assert setup["status"] == "mfa_setup" and setup["access_token"] == ""
    assert setup["otpauth_uri"].startswith("otpauth://totp/Afe:") and setup["totp_secret"]

    wrong = client.post("/api/v1/auth/mfa", json={"mfa_token": setup["mfa_token"], "code": "000000"})
    assert wrong.status_code == 401
    done = client.post(
        "/api/v1/auth/mfa", json={"mfa_token": setup["mfa_token"], "code": totp.now_code(setup["totp_secret"])}
    ).json()["data"]
    assert done["status"] == "signed_in" and done["user"]["mfa_enabled"]

    # Next time the code is required straight away.
    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "login"})
    again = client.post("/api/v1/auth/signin/code", json={"phone": PHONE, "code": sms_code()}).json()["data"]
    assert again["status"] == "mfa_required" and again["totp_secret"] == ""
    # An MFA token is not an access token.
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {again['mfa_token']}"}).status_code == 401


def test_only_renters_landlords_and_agents_can_sign_up(client, db):
    client.post("/api/v1/auth/code", json={"phone": PHONE, "purpose": "signup"})
    res = client.post(
        "/api/v1/auth/signup", json={"phone": PHONE, "code": sms_code(), "display_name": "Mallory", "role": "reviewer"}
    )
    assert res.status_code == 422


@pytest.mark.parametrize("url", ["/api/v1/me", "/api/v1/review/queue", "/api/v1/verify/worklist", "/api/v1/me/units"])
def test_protected_endpoints_need_a_token(client, url):
    assert client.get(url).status_code == 401


def test_roles_are_enforced(client, db):
    from tests.conftest import api_login

    make_user(db, "yaa", Role.RENTER)
    db.commit()
    renter = api_login(client, "yaa")
    for url in ("/api/v1/review/queue", "/api/v1/verify/worklist", "/api/v1/me/units"):
        assert client.get(url, headers=renter).status_code == 403


def test_username_sign_in_never_matches_another_phoneless_account(db):
    """`phone == None` is `IS NULL` in SQL: a username sign-in once matched every account
    without a phone, and PostgreSQL returned the wrong one."""
    from app.modules.accounts.service import authenticate

    make_user(db, "kwame", Role.FIELD_VERIFIER)
    efua = make_user(db, "efua", Role.REVIEWER)
    db.flush()
    assert authenticate(db, "efua", PASSWORD) is efua


def test_sign_up_records_consent_to_the_privacy_notice(client, db):
    from app.modules.accounts.privacy import NOTICE_VERSION

    phone = "+233240000123"
    client.post("/api/v1/auth/code", json={"phone": phone, "purpose": "signup"})
    refused = client.post("/api/v1/auth/signup", json={"phone": phone, "code": sms_code(phone), "display_name": "Abena",
                                                      "role": "renter"})
    assert refused.status_code == 422 and "privacy notice" in refused.json()["error"]["message"]
    client.post("/api/v1/auth/code", json={"phone": phone, "purpose": "signup"})
    res = client.post("/api/v1/auth/signup", json={"phone": phone, "code": sms_code(phone), "display_name": "Abena",
                                                  "role": "renter", "accept_privacy": True})
    token = res.json()["data"]["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()["data"]["user"]
    assert me["privacy_current"] is True
    user = db.scalar(select(User).where(User.phone == "+233240000123"))
    assert user.privacy_version == NOTICE_VERSION and user.privacy_accepted_at is not None
