"""Confirming move-in on WhatsApp.

The tenant sends "MOVED IN AFE-T-1A2B3C" from the phone number on their Afe account. Afe answers with the three
things the tenancy page asks them to check, and "YES AFE-T-1A2B3C" within 30 minutes confirms, exactly as the
page's button does. A message that doesn't match a tenancy of that number waiting for move-in gets the same
answer as a made-up reference, so the command can't be used to find out which references exist.
"""

import re
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFound
from app.core.ghana import format_ghs
from app.db import utcnow
from app.modules.accounts.models import RateEvent
from app.modules.audit.log import record

from . import service
from .models import Tenancy, TenancyStatus

ANSWER_WITHIN = timedelta(minutes=30)
REFERENCE = re.compile(r"\bAFE-T-[0-9A-F]{6}\b", re.IGNORECASE)
NOT_FOUND = (
    "There's no tenancy waiting for your move-in under that reference for this number. Send MOVED IN and the "
    "reference on your tenancy page (like AFE-T-1A2B3C), from the number on your Afe account."
)


def _waiting(db: Session, sender: str, words: str) -> Tenancy | None:
    match = REFERENCE.search(words)
    if match is None:
        return None
    try:
        # Locked, as on the tenancy page: a second YES waits for the first, then finds nothing waiting.
        tenancy = service.get_by_reference(db, match.group(0), lock=True)
    except NotFound:
        return None
    if tenancy.status != TenancyStatus.FUNDED:
        return None
    if tenancy.tenant.phone != sender or not tenancy.tenant.is_active:
        return None
    return tenancy


def _key(tenancy: Tenancy) -> str:
    return f"wa-movein:{tenancy.reference}"


def start(db: Session, sender: str, words: str) -> str:
    """MOVED IN <reference>: ask the tenant to check the three statements, then wait for YES."""
    tenancy = _waiting(db, sender, words)
    if tenancy is None:
        return NOT_FOUND
    db.execute(delete(RateEvent).where(RateEvent.key == _key(tenancy)))
    db.add(RateEvent(key=_key(tenancy)))
    db.flush()
    landlord = tenancy.landlord.name
    return (
        f"Before Afe releases {format_ghs(tenancy.payout_pesewas)} to {landlord}, check that all three are true:\n"
        "• I have the keys\n"
        "• The home matches the listing and photos\n"
        f"• I met the verified landlord, {landlord}\n"
        f"If they are, reply YES {tenancy.reference} within 30 minutes. If something is wrong, don't reply YES: "
        "tell us on the tenancy page on Afe."
    )


def confirm(db: Session, sender: str, words: str) -> str:
    """YES <reference>, within 30 minutes of MOVED IN: confirm the move-in, as the tenancy page does."""
    tenancy = _waiting(db, sender, words)
    if tenancy is None:
        return NOT_FOUND
    asked = db.scalar(
        select(RateEvent).where(RateEvent.key == _key(tenancy), RateEvent.created_at > utcnow() - ANSWER_WITHIN)
    )
    if asked is None:
        return f"Send MOVED IN {tenancy.reference} first, so we can check the details with you."
    try:
        # If the release is refused, undo the confirmation too, as the tenancy page does (it rolls back).
        with db.begin_nested():
            db.execute(delete(RateEvent).where(RateEvent.key == _key(tenancy)))
            service.confirm_move_in(db, tenancy.tenant, tenancy)
    except DomainError as exc:
        return str(exc)
    record(db, tenancy.tenant, "tenancy.move_in_whatsapp", tenancy)
    return f"Thank you. Your move-in is confirmed, and Afe will release the payment to {tenancy.landlord.name}."
