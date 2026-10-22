"""Product analytics events for the plan's metrics (§13). No personal data."""

from fastapi import APIRouter

from app.core.envelope import Envelope, ok
from app.deps import DB, MaybeUser
from app.modules.analytics.service import track

from .. import schemas as s

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=Envelope[dict], status_code=202)
def event(db: DB, user: MaybeUser, body: s.EventIn):
    track(db, body.name, user, body.anonymous_id, body.path, body.props)
    return ok({"recorded": True})
