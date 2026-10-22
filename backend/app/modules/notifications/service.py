"""Send notifications. Every event creates an in-app notification and, where the person can receive them, an
email and a text message. The text goes on WhatsApp to people who opted in (by SMS if WhatsApp can't deliver
it), and by SMS to everyone else. Events about money go by both.

Delivery happens inline for now. When Celery arrives (plan §8) the same rows become the
outbox: a worker picks up QUEUED rows and calls the providers.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.db import utcnow
from app.modules.accounts.models import Role, User

from .models import DeliveryStatus, Notification, NotificationChannel
from .providers import DeliveryError, provider_for
from .whatsapp_templates import MARKETING, whatsapp_template

# Plain, short texts: SMS costs money per 160 characters, and people read these on basic phones.
TEMPLATES: dict[str, tuple[str, str]] = {
    "pilot_report": (
        "Afe money today",
        "Held {held} of {limit}. Last 24h: {funded} paid in, {released} released, {refunded} refunded. "
        "{attention} need a person; {differences} reconciliation differences.",
    ),
    "model_report": (
        "Weekly model report",
        "Week {week}: {summary}. {seeded}.",
    ),
    "whatsapp_quality": (
        "WhatsApp number at risk",
        "Meta reports \"{event}\" for Afe's WhatsApp number {number}. Messaging limit: {limit}. Check its quality "
        "rating in WhatsApp Manager today.",
    ),
    "whatsapp_health": (
        "WhatsApp messages failing",
        "WhatsApp messages failed in the last day: {summary}. Check the templates and the number's quality rating "
        "in WhatsApp Manager.",
    ),
    "whatsapp_template": (
        "WhatsApp template needs attention",
        "Meta reports that the {name} WhatsApp template is {event}. Reword it and run "
        "python -m app.cli whatsapp-templates --submit; until then its messages may go by SMS.",
    ),
    "money_alert": ("Money needs a person", "{explanation} Tenancy {reference}. Open the money page on Afe today."),
    "money_reconcile": (
        "Reconciliation differences",
        "{count} difference(s) between Afe's ledger and the partner's statement, e.g. {example}. Open the money "
        "page on Afe today.",
    ),
    "money_cap": (
        "Pilot limit nearly reached",
        "Afe now holds or is collecting {held} of the {limit} pilot limit. Tenants can't accept offers once it's full.",
    ),
    "rent_due": ("Rent due soon", "{tenant}'s rent of {amount} is due on {when}."),
    "rent_overdue": ("Rent overdue", "{tenant}'s rent of {amount} was due on {when} and isn't recorded as paid."),
    "rent_due_tenant": ("Rent due soon", "Your rent of {amount} to {landlord} is due on {when}."),
    "rent_receipt": ("Rent receipt", "{landlord} recorded your payment of {amount}. Receipt {receipt} is on Afe."),
    "maintenance_raised": ("Repair request", "{tenant} asked for a repair: {title}."),
    "maintenance_updated": ("Repair update", "Your repair request \"{title}\" is now {status}."),
    "agreement_to_sign": ("Agreement to sign", "{landlord} sent you a tenancy agreement to sign on Afe."),
    "renewal_offered": ("Renewal offer", "{landlord} offers to renew your tenancy until {until} at {rent} a month."),
    "renewal_decided": ("Renewal", "{tenant} {result} your renewal offer."),
    "verification_expiring": (
        "Verification ends soon",
        "Afe's verification of {what} ends on {when}. We'll arrange a visit to renew it; your listings stay live until then.",
    ),
    "listing_paused_expired": (
        "Listing paused",
        "{listing} is paused because its verification ended. It goes live again when Afe renews it.",
    ),
    "appeal_decided": (
        "Your appeal",
        "Your appeal was {result}. {outcome}",
    ),
    "search_alert": (
        "New verified home",
        "New on Afe: {title}, {rent}/month in {area}. {url} Manage alerts in your Afe account.",
    ),
    "viewing_reminder_day": (
        "Viewing tomorrow",
        "Reminder: viewing of {listing} tomorrow at {when}. Never pay before you view.",
    ),
    "viewing_reminder_hour": (
        "Viewing in an hour",
        "Your viewing of {listing} is at {when}. If plans change, cancel on Afe so the other person knows.",
    ),
    "staff_invite": (
        "Welcome to the Afe team",
        "Hi {name}, you've been added to Afe's team. Sign in at {url} with this phone number: we'll text you a "
        "code, then you'll set up an authenticator app.",
    ),
    "otp": (
        "Your Afe code",
        "Your Afe code is {code}. It expires in 10 minutes. Afe will never ask you for this code.",
    ),
    "viewing_requested": (
        "New viewing request",
        "{renter} asked to view {listing} on {when}. Reply on Afe to confirm.",
    ),
    "viewing_confirmed": (
        "Viewing confirmed",
        "Your viewing of {listing} is confirmed for {when}. Never pay before you view.",
    ),
    "viewing_declined": (
        "Viewing not possible",
        "{lister} could not do {when} for {listing}. You can ask for another time on Afe.",
    ),
    "viewing_cancelled": ("Viewing cancelled", "The viewing of {listing} on {when} was cancelled."),
    "new_message": ("New message", "{sender} sent you a message about {listing} on Afe."),
    "listing_live": ("Your listing is live", "{listing} is now live on Afe as {reference}."),
    "party_verified": ("You are verified", "Afe has verified your identity. You can now list homes."),
    "party_rejected": (
        "Verification not approved",
        "Afe could not verify your identity. Open Afe to see what to do next.",
    ),
    "unit_verified": ("Home verified", "Afe has verified {unit}. You can now publish a listing for it."),
    "unit_rejected": ("Home not verified", "Afe could not verify {unit}. Open Afe to see why."),
    "visit_assigned": ("New visit", "You have a verification visit to {unit} on {when}."),
    "fee_paid": ("Payment received", "We received your verification fee of {amount} for {unit}. Receipt: {reference}."),
    "check_reply": ("", "{text}"),
    "tenancy_offered": ("Tenancy offer", "{landlord} offered you {listing}. Pay {amount} through Afe; it's held until you move in."),
    "tenancy_funded_tenant": ("Payment held safely", "Afe's partner is holding your {amount}. Confirm on Afe when you move in on {when}."),
    "tenancy_funded_landlord": ("Tenant has paid", "{tenant} paid {amount}, held until move-in on {when}. It's released when they confirm."),
    "tenancy_released": ("Payment released", "{amount} is on its way to {account}."),
    "tenancy_refunded": ("Refund sent", "Afe refunded {amount} to you."),
    "tenancy_review_invite": ("How was it?", "You've moved in. Review {landlord} on Afe to help other renters."),
    "dispute_opened": ("Problem raised", "{opener} raised a problem on tenancy {reference}. The money stays held while Afe reviews it."),
    "account_suspended": ("Account suspended", "Your Afe account is suspended while we check something. Any money held for you is safe. Contact Afe to sort it out."),
    "account_restored": ("Account restored", "Your Afe account is working again. You can sign in as normal."),
    "payee_changed": ("Payout account changed", "Your Afe payout account changed to {account}. It can receive money from {when}. Not you? Contact Afe now."),
    "review_received": ("New review", "A tenant left you a {rating}-star review on Afe."),
    "featured_paid": ("Listing featured", "{listing} is featured until {until}. Receipt: {reference}."),
}

SENSITIVE = {"otp"}
# Replies to someone who just wrote to Afe on WhatsApp: plain text, free inside the 24-hour window.
FREE_FORM = {"check_reply"}
# Events about money go by SMS as well as WhatsApp: a missed message about someone's money costs more than a
# second one.
BOTH_CHANNELS = {
    "tenancy_offered", "tenancy_funded_tenant", "tenancy_funded_landlord", "tenancy_released", "tenancy_refunded",
    "dispute_opened", "payee_changed", "fee_paid", "featured_paid",
}
# A failure reported later than this is about a stale notice: it isn't sent again by SMS.
FALLBACK_WITHIN = timedelta(hours=6)
# How long after a message's time-to-live Afe waits for Meta's delivery report before deciding it was dropped.
REPORT_GRACE = timedelta(minutes=10)
TTL_ERROR = "Not delivered within its time-to-live"


def _render(template: str, ctx: dict) -> tuple[str, str]:
    title, body = TEMPLATES[template]
    return title.format(**ctx), body.format(**ctx)


def _whatsapp_data(channel: str, template: str, ctx: dict) -> dict:
    """A WhatsApp row keeps its template's parameters, so a retry can send the template again. Never a code."""
    if channel != NotificationChannel.WHATSAPP or template in SENSITIVE or template in FREE_FORM:
        return {}
    return ctx


def _send_whatsapp(provider, note: Notification, body: str, ctx: dict | None) -> str:
    if note.template in FREE_FORM:
        return provider.send_text(note.recipient, body)
    template = whatsapp_template(note.template)
    if template is None:
        raise DeliveryError(f"No WhatsApp template for {note.template}")
    return provider.send_template(note.recipient, template, note.data if ctx is None else ctx)


def _deliver(db: Session, note: Notification, body: str, ctx: dict | None = None) -> Notification:
    """Send one row. ctx fills a WhatsApp template; without it (a retry) the row's stored parameters do."""
    provider = provider_for(note.channel)
    if provider is None:
        note.status, note.error = DeliveryStatus.FAILED, "No provider configured"
        return note
    note.attempts = (note.attempts or 0) + 1
    try:
        if note.channel == NotificationChannel.WHATSAPP:
            note.provider_ref = _send_whatsapp(provider, note, body, ctx)
        else:
            note.provider_ref = provider.send(note.recipient, body, note.title)
        note.provider, note.status, note.sent_at = provider.name, DeliveryStatus.SENT, utcnow()
    except DeliveryError as exc:
        note.provider, note.status, note.error = provider.name, DeliveryStatus.FAILED, str(exc)[:300]
    return note


def send_direct(
    db: Session, channel: str, recipient: str, template: str, user_id: int | None = None, **ctx
) -> Notification:
    """Send to an address that may not belong to an account yet (e.g. a sign-up code)."""
    title, body = _render(template, ctx)
    stored = _render(template, {**ctx, "code": "******"})[1] if template in SENSITIVE else body
    note = Notification(
        user_id=user_id, channel=channel, recipient=recipient, template=template, title=title, body=stored,
        data=_whatsapp_data(channel, template, ctx),
    )
    db.add(note)
    _deliver(db, note, body, ctx)
    db.flush()
    return note


def _text_channels(user, template: str) -> set[str]:
    """Where a text message goes: on WhatsApp to people who opted in, when the event has a template (not
    alerts, which follow the channel the person chose for them); by SMS otherwise. Money events go by both."""
    wa = whatsapp_template(template)
    if not (user.whatsapp_opt_in and wa is not None and wa.category != MARKETING):
        return {"sms"}
    return {"sms", "whatsapp"} if template in BOTH_CHANNELS else {"whatsapp"}


def fallback_to_sms(db: Session, note: Notification) -> Notification | None:
    """WhatsApp couldn't deliver a notice: send it by SMS, once, and stop trying WhatsApp. Not for sign-in
    codes (the code isn't stored: request_code, or a late failure report, sends a new one by SMS), replies, alerts
    (not worth a paid SMS), messages with no account, or money events (they went by SMS already)."""
    db.flush()  # the WhatsApp row needs its id and time
    wa = whatsapp_template(note.template)
    if (note.user_id is None or wa is None or wa.category == MARKETING or note.template in SENSITIVE
            or note.template in BOTH_CHANNELS or note.created_at < utcnow() - FALLBACK_WITHIN):
        return None
    note.attempts = MAX_ATTEMPTS
    sms = Notification(user_id=note.user_id, channel=NotificationChannel.SMS, recipient=note.recipient,
                       template=note.template, title=note.title, body=note.body, link=note.link,
                       fallback_of_id=note.id)
    db.add(sms)
    _deliver(db, sms, sms.body)
    db.flush()
    return sms


def _undelivered(db: Session, note: Notification, error: str) -> None:
    """WhatsApp won't deliver this message: stop trying it there, and get it to the person another way."""
    note.status, note.attempts, note.error = DeliveryStatus.FAILED, MAX_ATTEMPTS, error[:300]
    if note.template in SENSITIVE:
        from app.modules.accounts.service import resend_code_by_sms  # accounts imports this module

        resend_code_by_sms(db, note.recipient, sent_at=note.created_at)
    else:
        fallback_to_sms(db, note)


def _send(db: Session, notes: list[Notification], body: str, ctx: dict) -> list[Notification]:
    sent = []
    for note in notes:
        db.add(note)
        sent.append(note)
        if note.channel == NotificationChannel.IN_APP:
            continue
        _deliver(db, note, body, ctx)
        if note.channel == NotificationChannel.WHATSAPP and note.status == DeliveryStatus.FAILED:
            fallback = fallback_to_sms(db, note)
            if fallback is not None:
                sent.append(fallback)
    db.flush()
    return sent


def notify(db: Session, user, template: str, link: str = "", **ctx) -> list[Notification]:
    """Tell a person about an event on every channel they can receive: in the app, by email, and a text
    message (on WhatsApp or by SMS, see _text_channels)."""
    return notify_on(db, user, template, {"in_app", "sms", "email"}, link, **ctx)


def notify_on(db: Session, user, template: str, channels: set[str], link: str = "", **ctx) -> list[Notification]:
    """Like notify, but only on the channels given. "sms" asks for a text message, which goes on WhatsApp to
    people who opted in; "whatsapp" on its own is for someone who asked for it (an alert)."""
    title, body = _render(template, ctx)
    if "sms" in channels:
        channels = (set(channels) - {"sms"}) | _text_channels(user, template)
    if not user.whatsapp_opt_in:
        channels = set(channels) - {"whatsapp"}  # never on WhatsApp to someone who turned it off
    notes = []
    if "in_app" in channels:
        notes.append(Notification(user_id=user.id, channel=NotificationChannel.IN_APP, template=template, title=title,
                                  body=body, link=link, data=ctx, status=DeliveryStatus.SENT, sent_at=utcnow()))
    for channel, address in (("sms", user.phone), ("whatsapp", user.phone), ("email", user.email)):
        if channel in channels and address:
            notes.append(Notification(user_id=user.id, channel=channel, recipient=address, template=template,
                                      title=title, body=body, link=link, data=_whatsapp_data(channel, template, ctx)))
    return _send(db, notes, body, ctx)


def notify_admins(db: Session, template: str, link: str = "", **ctx) -> None:
    """Tell every active admin, in the app, by email and by SMS (staff messages never go on WhatsApp)."""
    for admin in db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))):
        notify_on(db, admin, template, {"in_app", "email", "sms"}, link, **ctx)


def inbox(db: Session, user, limit: int = 50) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id, Notification.channel == NotificationChannel.IN_APP)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
    )


def unread_count(db: Session, user) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.channel == NotificationChannel.IN_APP,
            Notification.read_at.is_(None),
        )
    )


def mark_read(db: Session, user, ids: list[int] | None = None) -> None:
    q = update(Notification).where(
        Notification.user_id == user.id,
        Notification.channel == NotificationChannel.IN_APP,
        Notification.read_at.is_(None),
    )
    if ids:
        q = q.where(Notification.id.in_(ids))
    db.execute(q.values(read_at=utcnow()))


MAX_ATTEMPTS = 3
RETRY_WITHIN = timedelta(hours=24)


def retry_failed(db: Session, limit: int = 500) -> dict[str, int]:
    """Try failed messages again (every few minutes): up to 3 attempts, waiting 5 then 30
    minutes, and never after a day. Sign-in codes aren't retried: a late code is useless, and
    only a masked copy is stored."""
    now = utcnow()
    waits = {1: timedelta(minutes=5), 2: timedelta(minutes=30)}
    rows = db.scalars(
        select(Notification)
        .where(
            Notification.status == DeliveryStatus.FAILED,
            Notification.channel != NotificationChannel.IN_APP,
            Notification.attempts < MAX_ATTEMPTS,
            Notification.created_at > now - RETRY_WITHIN,
            Notification.template.not_in(list(SENSITIVE)),
            # Not on WhatsApp to someone who has turned it off since.
            or_(Notification.channel != NotificationChannel.WHATSAPP, Notification.user_id.is_(None),
                Notification.user_id.in_(select(User.id).where(User.whatsapp_opt_in.is_(True)))),
        )
        .order_by(Notification.id)
        .limit(limit)
    )
    counts = {"sent": 0, "failed": 0, "waiting": 0}
    for note in rows:
        if note.created_at + waits.get(note.attempts, timedelta(0)) > now:
            counts["waiting"] += 1
            continue
        _deliver(db, note, note.body)
        counts["sent" if note.status == DeliveryStatus.SENT else "failed"] += 1
    db.flush()
    return counts


_PROGRESS = {DeliveryStatus.QUEUED: 0, DeliveryStatus.SENT: 1, DeliveryStatus.DELIVERED: 2, DeliveryStatus.READ: 3}


def _reported_at(timestamp) -> datetime:
    try:
        return datetime.fromtimestamp(int(timestamp), UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return utcnow()


def apply_whatsapp_status(db: Session, status: dict) -> Notification | None:
    """Meta's delivery report (sent, delivered, read or failed) for a message Afe sent. Reports can come late,
    twice or out of order, so a message only moves forward. A message that fails after Meta accepted it isn't
    sent on WhatsApp again: the notice goes by SMS instead."""
    ref = str(status.get("id") or "")
    note = ref and db.scalar(select(Notification).where(
        Notification.channel == NotificationChannel.WHATSAPP, Notification.provider_ref == ref
    ))
    if not note:
        return None
    state = status.get("status")
    if state == "failed" and note.status in (DeliveryStatus.QUEUED, DeliveryStatus.SENT):
        error = (status.get("errors") or [{}])[0]
        _undelivered(db, note, f"{error.get('code', '')}: {error.get('title', '')}")
    elif state in (DeliveryStatus.DELIVERED, DeliveryStatus.READ) and (
        _PROGRESS.get(note.status, len(_PROGRESS)) < _PROGRESS[state]
        # Arrived after all, after Afe gave up on it and sent the SMS: record it.
        or (note.status == DeliveryStatus.FAILED and note.error == TTL_ERROR)
    ):
        note.status = state
        note.delivered_at = note.delivered_at or _reported_at(status.get("timestamp"))
    db.flush()
    return note


def expire_undelivered(db: Session, now=None) -> dict:
    """Every few minutes: a WhatsApp message with no delivery report once its time-to-live has passed was
    dropped by Meta, which doesn't always say so; it goes by SMS instead. Only when some other message was
    reported delivered after this one's deadline: that shows reports were arriving, so a missing one means
    something. If reports stop (the webhook loses its subscription), nothing is resent."""
    now = now or utcnow()
    latest_report = db.scalar(select(func.max(Notification.delivered_at)).where(
        Notification.channel == NotificationChannel.WHATSAPP, Notification.created_at > now - timedelta(days=2)
    ))
    expired = 0
    if latest_report is not None:
        rows = db.scalars(select(Notification).where(
            Notification.channel == NotificationChannel.WHATSAPP, Notification.status == DeliveryStatus.SENT,
            Notification.created_at > now - FALLBACK_WITHIN, Notification.template.not_in(list(FREE_FORM)),
        ).order_by(Notification.id))
        for note in list(rows):
            wa = whatsapp_template(note.template)
            deadline = note.created_at + timedelta(seconds=wa.ttl_seconds) if wa else None
            if deadline is None or deadline + REPORT_GRACE > now or latest_report <= deadline:
                continue
            _undelivered(db, note, TTL_ERROR)
            expired += 1
        db.flush()
    return {"expired": expired, "reporting": latest_report is not None}
