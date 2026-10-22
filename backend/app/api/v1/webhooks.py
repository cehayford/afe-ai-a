"""WhatsApp: "Check before you pay" over WhatsApp (plan §1).

People message Afe's WhatsApp number with a phone number or listing reference and get the
same answer as the website. "REPORT <what happened>" files a scam report.
"""

import hashlib
import hmac
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import DomainError, InvalidInput, NotAllowed
from app.deps import DB
from app.modules.accounts.models import User
from app.modules.accounts.service import TooManyAttempts, rate_limit, set_whatsapp_opt_in
from app.modules.alerts import service as alerts
from app.modules.listings import service as listings_service
from app.modules.notifications import alarms
from app.modules.notifications.service import apply_whatsapp_status, send_direct
from app.modules.scamcheck import service as scamcheck
from app.modules.scamcheck.models import Channel
from app.modules.tenancies import whatsapp as move_in

router = APIRouter(prefix="/webhooks", tags=["webhooks"], include_in_schema=False)
log = logging.getLogger("afe.whatsapp")
# Every reply is a paid WhatsApp message; one person must not run up the bill.
WHATSAPP_LOOKUPS_PER_HOUR = 30

HELP = (
    "Hi, this is Afe. You can send:\n"
    "• a phone number or listing reference (like AFE-7K3M9Q) to check if Afe verified them\n"
    "• FIND 2 bed East Legon under 5000 to see verified homes\n"
    "• ALERT 2 bed East Legon under 5000 to be told when one is listed\n"
    "• STOP to stop alerts\n"
    "• REPORT and what happened, to report a scam"
)
MOVE_IN_HELP = "\n• MOVED IN and your tenancy reference (like AFE-T-1A2B3C), to confirm you've moved in"


def _help() -> str:
    return HELP + (MOVE_IN_HELP if get_settings().protected_payments_enabled else "")


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_subscription(
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
):
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
        return challenge
    raise NotAllowed("Verification failed.")


def _find(db, words: str) -> str:
    criteria = alerts.parse_query(db, words)
    homes = listings_service.search_live(
        db, criteria.area.slug if criteria.area else None, criteria.bedrooms, criteria.max_rent_pesewas, limit=3
    )
    what = alerts.describe(criteria.bedrooms, criteria.area, criteria.max_rent_pesewas)
    if not homes:
        return f"No verified homes match yet ({what}). Send ALERT {words} and we'll tell you when one is listed."
    url = get_settings().frontend_url
    lines = [f"Verified homes: {what}"]
    lines += [f"• {h.title}, {h.rent_display}/month, {h.unit.area.name}: {url}/homes/{h.reference}" for h in homes]
    lines.append("Book a viewing on the listing page. Never pay before you view.")
    return "\n".join(lines)


def _alert(db, sender: str, words: str) -> str:
    user = db.scalar(select(User).where(User.phone == sender, User.is_active.is_(True)))
    if user is None:
        return (f"To get alerts, create a free Afe account with this number at {get_settings().frontend_url}/signup, "
                f"then send ALERT {words} again.")
    try:
        search = alerts.save_search(db, user, alerts.parse_query(db, words), "whatsapp")
    except DomainError as exc:
        return str(exc)
    return f"Done. We'll message you here when a verified home is listed: {alerts.describe_search(search)}. Send STOP to stop."


def _stop(db, sender: str) -> str:
    user = db.scalar(select(User).where(User.phone == sender))
    if user is not None:
        alerts.stop_all(db, user)
        set_whatsapp_opt_in(db, user, False, "whatsapp_stop")
        db.flush()
    return "Stopped. You won't get Afe alerts on WhatsApp. Send HELP to see what else you can do."


def _reply_text(db, text: str, sender: str = "") -> str:
    text = text.strip()
    command, _, rest = text.partition(" ")
    command = command.upper()
    if command in ("FIND", "SEARCH", "HOMES"):
        return _find(db, rest)
    if command == "ALERT":
        return _alert(db, sender, rest)
    if command in ("STOP", "UNSUBSCRIBE"):
        return _stop(db, sender)
    if command in ("HELP", "HI", "HELLO", "MENU"):
        return _help()
    if command == "VIEW" and rest.strip():
        ref = rest.strip().split()[0].upper()
        return (f"Book a viewing of {ref} here: {get_settings().frontend_url}/homes/{ref}\n"
                "Afe never asks for a viewing fee.")
    if command == "MOVED" and rest.upper().startswith("IN"):
        return move_in.start(db, sender, rest)
    if command == "YES" and move_in.REFERENCE.search(rest):
        return move_in.confirm(db, sender, rest)
    if text.upper().startswith("REPORT"):
        what = text[6:].strip(" :-")
        try:
            scamcheck.report(db, what, channel=Channel.WHATSAPP)
        except InvalidInput:
            return "Please send REPORT followed by a sentence or two about what happened."
        return "Thank you. Your report has gone to the Afe trust team."
    result = scamcheck.check(db, text, channel=Channel.WHATSAPP)
    if not result.headline.startswith("Enter"):
        lines = [result.headline, *result.details, *(f"• {li.reference}: {li.title}" for li in result.listings)]
        lines += [f"• {a}" for a in result.advice]
        return "\n".join(lines)
    return _help()


@router.post("/whatsapp")
async def inbound(db: DB, request: Request):
    body = await request.body()
    secret = get_settings().whatsapp_app_secret
    if secret:
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
            raise NotAllowed("Bad signature.")
    elif not get_settings().debug:
        raise NotAllowed("WhatsApp is not configured.")
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "phone_number_quality_update":
                alarms.quality_update(db, change.get("value", {}))
                continue
            if change.get("field") in ("message_template_status_update", "template_category_update"):
                alarms.template_update(db, change["field"], change.get("value", {}))
                continue
            value = change.get("value", {})
            for status in value.get("statuses", []):
                apply_whatsapp_status(db, status)
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue
                sender = "+" + message["from"].lstrip("+")
                try:
                    rate_limit(db, f"whatsapp:{sender}", WHATSAPP_LOOKUPS_PER_HOUR, timedelta(hours=1), "")
                except TooManyAttempts:
                    log.info("whatsapp lookups limited for a sender")
                    continue
                reply = _reply_text(db, message["text"]["body"], sender)
                send_direct(db, "whatsapp", sender, "check_reply", text=reply)
    return {"ok": True}  # always 200 so Meta doesn't retry
