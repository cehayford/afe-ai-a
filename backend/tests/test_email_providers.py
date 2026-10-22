"""Email for the free development server: Resend's API or any SMTP service."""

import io
import json
import smtplib

import pytest

from app.config import get_settings
from app.modules.notifications import providers
from app.modules.notifications.providers import DeliveryError, ResendEmail, SmtpEmail


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_resend(monkeypatch):
    sent = []

    def urlopen(req, timeout=0):
        sent.append(req)
        return _Response(b'{"id": "re_123"}')

    monkeypatch.setattr(providers.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(get_settings(), "email_from", "Afe <hello@afe.example>")
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_key")
    assert ResendEmail().send("ama@example.com", "Your viewing is tomorrow.", "Viewing reminder") == "re_123"
    req = sent[0]
    assert req.full_url == "https://api.resend.com/emails" and req.headers["Authorization"] == "Bearer re_key"
    assert json.loads(req.data) == {"from": "Afe <hello@afe.example>", "to": ["ama@example.com"],
                                    "subject": "Viewing reminder", "text": "Your viewing is tomorrow."}
    monkeypatch.setattr(get_settings(), "resend_api_key", "")
    with pytest.raises(DeliveryError, match="not configured"):
        ResendEmail().send("ama@example.com", "hi")


class FakeSmtp:
    instances = []
    fail = False

    def __init__(self, host, port, timeout=0, context=None):
        self.host, self.port, self.steps = host, port, []
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.steps.append("starttls")

    def login(self, user, password):
        self.steps.append(("login", user))

    def send_message(self, msg):
        if FakeSmtp.fail:
            raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no")})
        self.steps.append(("send", msg["To"], msg["Subject"], msg.get_content().strip()))


def test_smtp(monkeypatch):
    FakeSmtp.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    s = get_settings()
    monkeypatch.setattr(s, "email_from", "Afe <hello@afe.example>")
    monkeypatch.setattr(s, "smtp_host", "smtp-relay.brevo.com")
    monkeypatch.setattr(s, "smtp_username", "user")
    monkeypatch.setattr(s, "smtp_password", "pw")
    ref = SmtpEmail().send("ama@example.com", "Body text", "Subject")
    assert ref.endswith("@afe.example>")
    server = FakeSmtp.instances[-1]
    assert (server.host, server.port) == ("smtp-relay.brevo.com", 587)
    assert server.steps == ["starttls", ("login", "user"), ("send", "ama@example.com", "Subject", "Body text")]

    monkeypatch.setattr(s, "smtp_security", "ssl")
    monkeypatch.setattr(s, "smtp_port", 465)
    SmtpEmail().send("ama@example.com", "Body")
    assert "starttls" not in FakeSmtp.instances[-1].steps

    FakeSmtp.fail = True
    try:
        with pytest.raises(DeliveryError, match="SMTP refused"):
            SmtpEmail().send("ama@example.com", "Body")
    finally:
        FakeSmtp.fail = False
