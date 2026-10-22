"""Saved homes, enquiries, messages and viewings (plan Sprint 3)."""

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, NotFound, RuleViolation
from app.db import utcnow
from app.modules.audit.log import record
from app.modules.detection.hooks import enqueue_text
from app.modules.listings.models import Listing, ListingStatus
from app.modules.notifications.models import Notification
from app.modules.notifications.service import notify, notify_on
from app.modules.risk.flags import raise_flag
from app.modules.risk.models import Severity
from app.modules.risk.rules import scam_language

from .models import OPEN_VIEWING, Message, SavedListing, Thread, Viewing, ViewingStatus

MAX_MESSAGE = 2000
PAY_FIRST_WARNING = "Afe warning: this message talks about paying before a viewing. Never pay before you view."
OFF_PLATFORM_WARNING = "Afe warning: keep the conversation and any payment on Afe so we can protect you."


def _when(dt: datetime) -> str:
    return dt.strftime("%a %d %b, %H:%M")


# --- Saved homes -----------------------------------------------------------------------------------


def save_listing(db: Session, user, listing: Listing) -> SavedListing:
    existing = db.scalar(
        select(SavedListing).where(SavedListing.user_id == user.id, SavedListing.listing_id == listing.id)
    )
    if existing:
        return existing
    saved = SavedListing(user_id=user.id, listing_id=listing.id)
    db.add(saved)
    db.flush()
    return saved


def unsave_listing(db: Session, user, listing: Listing) -> None:
    saved = db.scalar(
        select(SavedListing).where(SavedListing.user_id == user.id, SavedListing.listing_id == listing.id)
    )
    if saved:
        db.delete(saved)
        db.flush()


def saved_listings(db: Session, user) -> list[Listing]:
    return list(
        db.scalars(
            select(Listing)
            .join(SavedListing, SavedListing.listing_id == Listing.id)
            .where(SavedListing.user_id == user.id, Listing.status == ListingStatus.LIVE)
            .order_by(SavedListing.created_at.desc())
        )
    )


# --- Threads and messages ------------------------------------------------------------------------------


def _require_live(listing: Listing) -> None:
    if listing.status != ListingStatus.LIVE:
        raise RuleViolation("This home is not live on Afe right now.")


def _thread_for(db: Session, renter, listing: Listing) -> Thread:
    if renter.id == listing.lister_id:
        raise RuleViolation("You can't enquire about your own listing.")
    if renter.is_staff:
        raise NotAllowed("Afe staff can't send enquiries.")
    thread = db.scalar(select(Thread).where(Thread.listing_id == listing.id, Thread.renter_id == renter.id))
    if thread is None:
        thread = Thread(listing_id=listing.id, renter_id=renter.id, lister_id=listing.lister_id)
        try:
            with db.begin_nested():
                db.add(thread)
                db.flush()
        except IntegrityError:
            thread = db.scalar(select(Thread).where(Thread.listing_id == listing.id, Thread.renter_id == renter.id))
    return thread


def start_enquiry(db: Session, renter, listing: Listing, body: str) -> Thread:
    _require_live(listing)
    thread = _thread_for(db, renter, listing)
    send_message(db, thread, renter, body)
    return thread


def _participant(thread: Thread, user) -> None:
    if user.id not in (thread.renter_id, thread.lister_id):
        raise NotFound("Conversation not found.")


def send_message(db: Session, thread: Thread, sender, body: str) -> Message:
    _participant(thread, sender)
    body = (body or "").strip()
    if not body:
        raise InvalidInput("Write a message.")
    if len(body) > MAX_MESSAGE:
        raise InvalidInput(f"Keep messages under {MAX_MESSAGE} characters.")

    hits = scam_language(body)
    warning = ""
    if any(h.rule == "language.pay_before_viewing" for h in hits):
        warning = PAY_FIRST_WARNING
    elif any(h.rule in ("language.move_off_platform", "language.phone_number_in_text") for h in hits):
        warning = OFF_PLATFORM_WARNING
    message = Message(thread_id=thread.id, sender_id=sender.id, body=body, warning=warning)
    db.add(message)
    now = utcnow()
    thread.last_message_at = now
    if sender.id == thread.renter_id:
        thread.renter_read_at = now
    else:
        thread.lister_read_at = now
    db.flush()

    # A lister asking for money before a viewing is the scam this product exists to stop.
    for hit in hits:
        if sender.id == thread.lister_id and hit.severity == Severity.HIGH:
            raise_flag(
                db,
                sender,
                f"message.{hit.rule}",
                Severity.HIGH,
                f"In a message to a renter: {hit.explanation}",
                thread=thread.id,
                message=message.id,
            )

    enqueue_text(db, message)
    _notify_new_message(db, thread, sender)
    return message


def _notify_new_message(db: Session, thread: Thread, sender) -> None:
    """At most one message notification per conversation every 15 minutes, so a chat
    doesn't become a stream of paid SMS."""
    recipient = thread.other(sender)
    recent = db.scalar(
        select(Notification.id).where(
            Notification.user_id == recipient.id,
            Notification.template == "new_message",
            Notification.created_at > utcnow() - timedelta(minutes=15),
            Notification.link == f"/account/messages/{thread.id}",
        )
    )
    if recent is None:
        notify(
            db,
            recipient,
            "new_message",
            link=f"/account/messages/{thread.id}",
            sender=sender.name,
            listing=thread.listing.title,
        )


def threads_for(db: Session, user) -> list[Thread]:
    return list(
        db.scalars(
            select(Thread)
            .where(or_(Thread.renter_id == user.id, Thread.lister_id == user.id))
            .order_by(Thread.last_message_at.desc())
        )
    )


def open_thread(db: Session, thread_id: int, user) -> Thread:
    thread = db.get(Thread, thread_id)
    if thread is None:
        raise NotFound("Conversation not found.")
    _participant(thread, user)
    if user.id == thread.renter_id:
        thread.renter_read_at = utcnow()
    else:
        thread.lister_read_at = utcnow()
    db.flush()
    return thread


def _system_message(db: Session, thread: Thread, body: str) -> None:
    db.add(Message(thread_id=thread.id, sender_id=None, body=body))
    thread.last_message_at = utcnow()
    db.flush()


# --- Viewings -------------------------------------------------------------------------------------------------


def request_viewing(db: Session, renter, listing: Listing, when: datetime, note: str = "") -> Viewing:
    _require_live(listing)
    if when.tzinfo is None:
        raise InvalidInput("Give the viewing time with a timezone.")
    now = utcnow()
    if when < now + timedelta(hours=1):
        raise InvalidInput("Choose a time at least an hour from now.")
    if when > now + timedelta(days=60):
        raise InvalidInput("Choose a time within the next two months.")
    thread = _thread_for(db, renter, listing)
    open_one = db.scalar(
        select(Viewing).where(
            Viewing.listing_id == listing.id,
            Viewing.renter_id == renter.id,
            Viewing.status.in_([str(s) for s in OPEN_VIEWING]),
        )
    )
    if open_one:
        raise RuleViolation("You already have a viewing booked for this home. Cancel it to choose another time.")
    viewing = Viewing(
        listing_id=listing.id,
        thread_id=thread.id,
        renter_id=renter.id,
        lister_id=listing.lister_id,
        requested_for=when,
        note=note.strip()[:300],
    )
    db.add(viewing)
    db.flush()
    _system_message(db, thread, f"{renter.name} asked to view the home on {_when(when)}.")
    notify(
        db,
        listing.lister,
        "viewing_requested",
        link="/landlord/viewings",
        renter=renter.name,
        listing=listing.title,
        when=_when(when),
    )
    record(db, renter, "viewing.requested", viewing)
    return viewing


def respond_viewing(db: Session, viewing: Viewing, lister, confirm: bool, note: str = "") -> Viewing:
    if viewing.lister_id != lister.id:
        raise NotFound("Viewing not found.")
    if viewing.status != ViewingStatus.REQUESTED:
        raise RuleViolation("This viewing has already been answered.")
    viewing.status = ViewingStatus.CONFIRMED if confirm else ViewingStatus.DECLINED
    viewing.response_note = note.strip()[:300]
    viewing.responded_at = utcnow()
    db.flush()
    thread = db.get(Thread, viewing.thread_id)
    when = _when(viewing.requested_for)
    if confirm:
        _system_message(db, thread, f"Viewing confirmed for {when}. Never pay before you have seen the home.")
        notify(
            db, viewing.renter, "viewing_confirmed", link="/account/viewings", listing=viewing.listing.title, when=when
        )
    else:
        _system_message(
            db,
            thread,
            f"{lister.name} can't do {when}." + (f" {viewing.response_note}" if viewing.response_note else ""),
        )
        notify(
            db,
            viewing.renter,
            "viewing_declined",
            link="/account/viewings",
            lister=lister.name,
            listing=viewing.listing.title,
            when=when,
        )
    record(db, lister, "viewing.responded", viewing, status=viewing.status)
    return viewing


def cancel_viewing(db: Session, viewing: Viewing, user) -> Viewing:
    if user.id not in (viewing.renter_id, viewing.lister_id):
        raise NotFound("Viewing not found.")
    if viewing.status not in OPEN_VIEWING:
        raise RuleViolation("Only upcoming viewings can be cancelled.")
    viewing.status = ViewingStatus.CANCELLED
    db.flush()
    other = viewing.lister if user.id == viewing.renter_id else viewing.renter
    when = _when(viewing.requested_for)
    _system_message(db, db.get(Thread, viewing.thread_id), f"{user.name} cancelled the viewing on {when}.")
    notify(db, other, "viewing_cancelled", link="/account/viewings", listing=viewing.listing.title, when=when)
    record(db, user, "viewing.cancelled", viewing)
    return viewing


def complete_viewing(db: Session, viewing: Viewing, lister, attended: bool) -> Viewing:
    if viewing.lister_id != lister.id:
        raise NotFound("Viewing not found.")
    if viewing.status != ViewingStatus.CONFIRMED:
        raise RuleViolation("Only confirmed viewings can be marked as done.")
    if viewing.requested_for > utcnow():
        raise RuleViolation("You can mark the viewing as done after it has happened.")
    viewing.status = ViewingStatus.COMPLETED if attended else ViewingStatus.NO_SHOW
    viewing.completed_at = utcnow()
    db.flush()
    record(db, lister, "viewing.completed", viewing, attended=attended)
    return viewing


def viewings_for(db: Session, user) -> list[Viewing]:
    return list(
        db.scalars(
            select(Viewing)
            .where(or_(Viewing.renter_id == user.id, Viewing.lister_id == user.id))
            .order_by(Viewing.requested_for.desc())
        )
    )


def send_viewing_reminders(db: Session) -> dict[str, int]:
    """Every few minutes: remind both people a day before and an hour before a confirmed
    viewing. Reminders cut no-shows, and repeat the one rule that matters: never pay first."""
    now = utcnow()
    counts = {"day": 0, "hour": 0}
    windows = (
        ("day", "viewing_reminder_day", Viewing.reminded_day_at, timedelta(hours=20), timedelta(hours=26)),
        ("hour", "viewing_reminder_hour", Viewing.reminded_hour_at, timedelta(minutes=40), timedelta(minutes=80)),
    )
    for key, template, column, start, end in windows:
        due = db.scalars(select(Viewing).where(
            Viewing.status == ViewingStatus.CONFIRMED, column.is_(None),
            Viewing.requested_for > now + start, Viewing.requested_for <= now + end,
        ))
        for viewing in due:
            for person in (viewing.renter, viewing.lister):
                if person.is_active:
                    notify_on(db, person, template, {"in_app", "sms"}, link="/account/viewings",
                              listing=viewing.listing.title, when=_when(viewing.requested_for))
            setattr(viewing, column.key, now)
            counts[key] += 1
    db.flush()
    return counts
