"""Field visits: what the field-verifier app calls."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Form, UploadFile

from app.config import get_settings
from app.core.envelope import Envelope, ok
from app.core.errors import InvalidInput, NotFound
from app.deps import DB, Verifier
from app.modules.units.models import Unit
from app.modules.verification import service as verification
from app.modules.verification.models import CHECKLIST_ITEMS, PHOTO_CAPTIONS, FieldVisit, VisitAssignment

from .. import schemas as s
from .common import MAX_PHOTO_BYTES, get_or_404, read_upload

router = APIRouter(prefix="/verify", tags=["verify"])


def visit_detail_out(visit: FieldVisit) -> s.VisitDetailOut:
    settings = get_settings()
    return s.VisitDetailOut.of(
        visit, CHECKLIST_ITEMS, PHOTO_CAPTIONS, settings.min_visit_photos, settings.field_visit_radius_m
    )


@router.get("/worklist", response_model=Envelope[s.WorklistOut])
def worklist(db: DB, user: Verifier):
    """Open assignments (by scheduled date) and visits in progress for the signed-in verifier."""
    assignments, in_progress = verification.verifier_worklist(db, user)
    return ok(
        s.WorklistOut(
            assignments=[s.AssignmentOut.of(a) for a in assignments],
            in_progress=[s.VisitOut.model_validate(v) for v in in_progress],
            radius_m=get_settings().field_visit_radius_m,
        )
    )


@router.get("/assignments/{assignment_id}", response_model=Envelope[s.AssignmentOut])
def assignment(db: DB, user: Verifier, assignment_id: int):
    a = get_or_404(db, VisitAssignment, assignment_id, "Assignment")
    if a.verifier_id != user.id:
        raise NotFound("Assignment not found.")
    return ok(s.AssignmentOut.of(a))


@router.get("/visits/{visit_id}", response_model=Envelope[s.VisitDetailOut])
def visit_detail(db: DB, user: Verifier, visit_id: int):
    visit = get_or_404(db, FieldVisit, visit_id, "Visit")
    if visit.verifier_id != user.id:
        raise NotFound("Visit not found.")
    return ok(visit_detail_out(visit))


@router.post("/visits", response_model=Envelope[s.VisitOut], status_code=201)
def start_visit(db: DB, user: Verifier, body: s.VisitStartIn):
    """Check in at the property. Needs an open assignment and a location within the radius.
    Calling it again for the same home resumes the visit already in progress."""
    visit = verification.start_visit(db, get_or_404(db, Unit, body.unit_id, "Home"), user, body.lat, body.lng)
    return ok(s.VisitOut.model_validate(visit))


@router.post("/visits/{visit_id}/photos", response_model=Envelope[s.PhotoOut], status_code=201)
async def add_photo(
    db: DB,
    user: Verifier,
    visit_id: int,
    photo: UploadFile,
    lat: Annotated[Decimal, Form()],
    lng: Annotated[Decimal, Form()],
    taken_at: Annotated[datetime, Form(description="ISO 8601 with timezone")],
    caption: Annotated[str, Form(max_length=80)] = "",
    client_ref: Annotated[str | None, Form(max_length=64, description="Unique per photo; makes retries safe")] = None,
):
    if taken_at.tzinfo is None:
        raise InvalidInput("taken_at must include a timezone, e.g. 2026-11-14T10:30:00Z.")
    visit = get_or_404(db, FieldVisit, visit_id, "Visit")
    data = await read_upload(photo, MAX_PHOTO_BYTES)
    saved = verification.add_visit_photo(db, visit, user, data, lat, lng, taken_at, caption, client_ref)
    return ok(s.PhotoOut.of(saved), duplicate=saved.duplicate_of_id is not None)


@router.post("/visits/{visit_id}/complete", response_model=Envelope[s.VisitOut])
def complete_visit(db: DB, user: Verifier, visit_id: int, body: s.VisitCompleteIn):
    visit = verification.complete_visit(
        db, get_or_404(db, FieldVisit, visit_id, "Visit"), user, body.checklist, body.notes,
        body.travel_minutes, round(body.transport_ghs * 100) if body.transport_ghs is not None else None,
        result=body.result, fail_reason=body.fail_reason,
    )
    return ok(s.VisitOut.model_validate(visit))
