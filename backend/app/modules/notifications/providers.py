"""Delivery providers, one per channel, behind one small interface. Swap a fake for a real
provider in settings (AFE_SMS_PROVIDER, AFE_WHATSAPP_PROVIDER, AFE_EMAIL_PROVIDER).

Real providers: WhatsAppCloud (Meta's WhatsApp Business Cloud API), HubtelSms (a Ghana SMS
gateway) and SesEmail (Amazon SES). For the free development server: ResendEmail (Resend's API)
or SmtpEmail (any SMTP service, e.g. Brevo or Resend's SMTP). Check each against the live account in staging before
launch: sender IDs, templates and rate limits are account settings, not code.

WhatsApp providers have two calls instead of `send`: `send_template` for messages Afe starts (each event has its
own approved template, see whatsapp_templates.py) and `send_text` for a reply to someone who just wrote.
"""

import importlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings

log = logging.getLogger("afe.notifications")


class DeliveryError(Exception):
    pass


class Provider(Protocol):
    name: str

    def send(self, recipient: str, body: str, title: str = "") -> str:
        """Deliver the message and return the provider's reference."""


class WhatsAppProvider(Protocol):
    name: str

    def send_template(self, recipient: str, template, ctx: dict) -> str:
        """Send an approved template with its parameters filled from ctx; return Meta's message id."""

    def send_text(self, recipient: str, body: str) -> str:
        """Send a free-form reply (only inside the 24-hour customer service window)."""


@dataclass
class SentMessage:
    channel: str
    recipient: str
    body: str
    title: str = ""


@dataclass
class FakeOutbox:
    """Everything the fake providers "sent", for development and tests."""

    messages: list[SentMessage] = field(default_factory=list)

    def last(self, channel: str, recipient: str) -> SentMessage | None:
        return next((m for m in reversed(self.messages) if m.channel == channel and m.recipient == recipient), None)

    def clear(self) -> None:
        self.messages.clear()


fake_outbox = FakeOutbox()


class _Fake:
    channel = ""

    @property
    def name(self) -> str:
        return f"fake-{self.channel}"

    def send(self, recipient: str, body: str, title: str = "") -> str:
        fake_outbox.messages.append(SentMessage(self.channel, recipient, body, title))
        log.info("[%s to %s] %s", self.channel, recipient, body)  # dev only: shows sign-in codes in the console
        return f"fake-{secrets.token_hex(6)}"


class FakeSms(_Fake):
    channel = "sms"


class FakeWhatsApp(_Fake):
    """Records what the person would see: the template's wording with its parameters filled in."""

    channel = "whatsapp"

    def send_template(self, recipient: str, template, ctx: dict) -> str:
        return self.send(recipient, template.render(ctx))

    def send_text(self, recipient: str, body: str) -> str:
        return self.send(recipient, body)


class FakeEmail(_Fake):
    channel = "email"


# --- Real providers -------------------------------------------------------------------------------


def _request(url: str, payload: dict | None, headers: dict[str, str], what: str, timeout: int = 15) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "User-Agent": "afe/1.0", **headers}
    req = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - fixed https URLs
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="replace")
        raise DeliveryError(f"{what} refused the message ({exc.code}): {detail}") from exc
    except OSError as exc:
        raise DeliveryError(f"{what} is unreachable: {exc}") from exc


def _digits(phone: str) -> str:
    return phone.lstrip("+")


class WhatsAppCloud:
    """Meta's WhatsApp Business Cloud API. Messages Afe starts go through the approved template for their
    event; replies inside the 24-hour customer service window go as plain text, which is free."""

    name = "whatsapp-cloud"
    channel = "whatsapp"

    def send_template(self, recipient: str, template, ctx: dict) -> str:
        return self._post(recipient, {"type": "template", "template": template.message(ctx)})

    def send_text(self, recipient: str, body: str) -> str:
        return self._post(recipient, {"type": "text", "text": {"preview_url": False, "body": body[:4096]}})

    def _post(self, recipient: str, message: dict) -> str:
        s = get_settings()
        if not (s.whatsapp_phone_number_id and s.whatsapp_access_token):
            raise DeliveryError("WhatsApp is not configured")
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": _digits(recipient), **message}
        data = _request(
            f"https://graph.facebook.com/{s.whatsapp_graph_version}/{s.whatsapp_phone_number_id}/messages",
            payload,
            {"Authorization": f"Bearer {s.whatsapp_access_token}"},
            "WhatsApp",
        )
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise DeliveryError(f"WhatsApp gave no message id: {str(data)[:200]}") from exc


class HubtelSms:
    """Hubtel's SMS API. The sender ID ("Afe") must be registered on the Hubtel account."""

    name = "hubtel"
    channel = "sms"
    URL = "https://smsc.hubtel.com/v1/messages/send"

    def send(self, recipient: str, body: str, title: str = "") -> str:
        s = get_settings()
        if not (s.hubtel_client_id and s.hubtel_client_secret):
            raise DeliveryError("Hubtel is not configured")
        query = urllib.parse.urlencode({
            "clientid": s.hubtel_client_id,
            "clientsecret": s.hubtel_client_secret,
            "from": s.sms_sender_id,
            "to": _digits(recipient),
            "content": body[:459],  # three SMS parts at most
        })
        data = _request(f"{self.URL}?{query}", None, {}, "Hubtel")
        if str(data.get("status", "0")) not in ("0", "success"):
            raise DeliveryError(f"Hubtel refused the message: {str(data)[:200]}")
        return str(data.get("messageId") or data.get("MessageId") or "")


class SesEmail:
    """Amazon SES. The sending address's domain must be verified in SES (Terraform does it)."""

    name = "ses"
    channel = "email"

    def send(self, recipient: str, body: str, title: str = "") -> str:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        s = get_settings()
        if not s.email_from:
            raise DeliveryError("AFE_EMAIL_FROM is not set")
        client = boto3.client("ses", region_name=s.ses_region or s.s3_region)
        try:
            res = client.send_email(
                Source=s.email_from,
                Destination={"ToAddresses": [recipient]},
                Message={"Subject": {"Data": title or "Afe"}, "Body": {"Text": {"Data": body}}},
            )
        except (BotoCoreError, ClientError) as exc:
            raise DeliveryError(f"SES refused the message: {exc}") from exc
        return res["MessageId"]


class ResendEmail:
    """Resend (resend.com). Free: 3,000 emails a month, 100 a day. The sending domain must be
    verified in Resend; until then only the account owner's address can receive."""

    name = "resend"
    channel = "email"
    URL = "https://api.resend.com/emails"

    def send(self, recipient: str, body: str, title: str = "") -> str:
        s = get_settings()
        if not (s.resend_api_key and s.email_from):
            raise DeliveryError("Resend is not configured: set AFE_RESEND_API_KEY and AFE_EMAIL_FROM")
        data = _request(
            self.URL,
            {"from": s.email_from, "to": [recipient], "subject": title or "Afe", "text": body},
            {"Authorization": f"Bearer {s.resend_api_key}"},
            "Resend",
        )
        if not data.get("id"):
            raise DeliveryError(f"Resend gave no message id: {str(data)[:200]}")
        return data["id"]


class SmtpEmail:
    """Any SMTP service (Brevo, Resend SMTP, Mailgun, a Gmail app password). STARTTLS on 587
    by default; AFE_SMTP_SECURITY=ssl for port 465."""

    name = "smtp"
    channel = "email"

    def send(self, recipient: str, body: str, title: str = "") -> str:
        import smtplib
        import ssl
        from email.message import EmailMessage
        from email.utils import make_msgid, parseaddr

        s = get_settings()
        if not (s.smtp_host and s.email_from):
            raise DeliveryError("SMTP is not configured: set AFE_SMTP_HOST and AFE_EMAIL_FROM")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.email_from, recipient, title or "Afe"
        msg["Message-ID"] = make_msgid(domain=parseaddr(s.email_from)[1].rpartition("@")[2] or None)
        msg.set_content(body)
        context = ssl.create_default_context()
        try:
            if s.smtp_security == "ssl":
                server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=context)
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
            with server:
                if s.smtp_security == "starttls":
                    server.starttls(context=context)
                if s.smtp_username:
                    server.login(s.smtp_username, s.smtp_password)
                server.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise DeliveryError(f"SMTP refused the message: {exc}") from exc
        return msg["Message-ID"]


def _load(path: str) -> Provider:
    module, _, cls = path.rpartition(".")
    return getattr(importlib.import_module(module), cls)()


def provider_for(channel: str) -> Provider | WhatsAppProvider | None:
    s = get_settings()
    path = {"sms": s.sms_provider, "whatsapp": s.whatsapp_provider, "email": s.email_provider}.get(channel)
    return _load(path) if path else None
