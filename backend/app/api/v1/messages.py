"""Conversations and viewings between renters and listers."""

from fastapi import APIRouter

from app.core.envelope import Envelope, ok
from app.core.errors import NotFound
from app.deps import DB, ApiUser, Lister
from app.modules.enquiries import service as enquiries
from app.modules.enquiries.models import Thread, Viewing
from app.modules.insights import service as insights

from .. import schemas as s
from .common import get_or_404

router = APIRouter(tags=["messages"])


def thread_out(thread: Thread, user) -> s.ThreadOut:
    return s.ThreadOut(
        id=thread.id,
        listing_reference=thread.listing.reference,
        listing_title=thread.listing.title,
        other_name=thread.other(user).name,
        role="renter" if user.id == thread.renter_id else "lister",
        last_message_at=thread.last_message_at,
        unread=thread.unread_for(user),
    )


def viewing_out(viewing: Viewing, user) -> s.ViewingOut:
    as_renter = user.id == viewing.renter_id
    return s.ViewingOut(
        id=viewing.id,
        listing_reference=viewing.listing.reference,
        listing_title=viewing.listing.title,
        other_name=(viewing.lister if as_renter else viewing.renter).name,
        role="renter" if as_renter else "lister",
        requested_for=viewing.requested_for,
        status=viewing.status,
        note=viewing.note,
        response_note=viewing.response_note,
        thread_id=viewing.thread_id,
        outcome=viewing.outcome.answer if as_renter and viewing.outcome else None,
    )


@router.get("/messages", response_model=Envelope[list[s.ThreadOut]])
def threads(db: DB, user: ApiUser):
    return ok([thread_out(t, user) for t in enquiries.threads_for(db, user)])


@router.get("/messages/{thread_id}", response_model=Envelope[s.ThreadDetailOut])
def thread(db: DB, user: ApiUser, thread_id: int):
    t = enquiries.open_thread(db, thread_id, user)
    viewings = [v for v in enquiries.viewings_for(db, user) if v.thread_id == t.id]
    return ok(
        s.ThreadDetailOut(
            **thread_out(t, user).model_dump(),
            messages=[
                s.MessageOut(
                    id=m.id,
                    sender="Afe" if m.sender_id is None else ("You" if m.sender_id == user.id else m.sender.name),
                    mine=m.sender_id == user.id,
                    system=m.sender_id is None,
                    body=m.body,
                    # Warnings are for the person reading someone else's message.
                    warning=m.warning if m.sender_id not in (None, user.id) else "",
                    created_at=m.created_at,
                )
                for m in t.messages
            ],
            viewings=[viewing_out(v, user) for v in viewings],
        )
    )


@router.post("/messages/{thread_id}", response_model=Envelope[s.MessageOut], status_code=201)
def send(db: DB, user: ApiUser, thread_id: int, body: s.EnquiryIn):
    t = get_or_404(db, Thread, thread_id, "Conversation")
    m = enquiries.send_message(db, t, user, body.body)
    return ok(
        s.MessageOut(id=m.id, sender="You", mine=True, system=False, body=m.body, warning="", created_at=m.created_at)
    )


@router.get("/viewings", response_model=Envelope[list[s.ViewingOut]])
def viewings(db: DB, user: ApiUser):
    return ok([viewing_out(v, user) for v in enquiries.viewings_for(db, user)])


def _viewing(db, viewing_id, user) -> Viewing:
    v = get_or_404(db, Viewing, viewing_id, "Viewing")
    if user.id not in (v.renter_id, v.lister_id):
        raise NotFound("Viewing not found.")
    return v


@router.post("/viewings/{viewing_id}/respond", response_model=Envelope[s.ViewingOut])
def respond(db: DB, user: Lister, viewing_id: int, body: s.ViewingRespondIn):
    v = enquiries.respond_viewing(db, _viewing(db, viewing_id, user), user, body.confirm, body.note)
    return ok(viewing_out(v, user))


@router.post("/viewings/{viewing_id}/cancel", response_model=Envelope[s.ViewingOut])
def cancel(db: DB, user: ApiUser, viewing_id: int):
    return ok(viewing_out(enquiries.cancel_viewing(db, _viewing(db, viewing_id, user), user), user))


@router.post("/viewings/{viewing_id}/complete", response_model=Envelope[s.ViewingOut])
def complete(db: DB, user: Lister, viewing_id: int, body: s.ViewingCompleteIn):
    v = enquiries.complete_viewing(db, _viewing(db, viewing_id, user), user, body.attended)
    return ok(viewing_out(v, user))



@router.post("/viewings/{viewing_id}/outcome", response_model=Envelope[s.ViewingOut])
def outcome(db: DB, user: ApiUser, viewing_id: int, body: s.ViewingOutcomeIn):
    """After a viewing: did you rent it, and did you pay through Afe?"""
    viewing = _viewing(db, viewing_id, user)
    insights.record_outcome(db, user, viewing, body.answer)
    return ok(viewing_out(viewing, user))
