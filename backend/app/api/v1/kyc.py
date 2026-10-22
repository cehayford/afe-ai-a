"""Identity (Ghana Card) and authority documents for landlords and agents."""

from typing import Annotated

from fastapi import APIRouter, Form, UploadFile

from app.core.envelope import Envelope, ok
from app.core.errors import NotAllowed
from app.deps import DB, Lister
from app.modules.identity.service import check_ghana_card, latest_check
from app.modules.units import service as units
from app.modules.units.models import Unit

from .. import schemas as s
from .common import MAX_PHOTO_BYTES, get_or_404, keep_attempts, read_upload

router = APIRouter(prefix="/kyc", tags=["kyc"])


@router.post("/ghana-card", response_model=Envelope[s.IdentityCheckOut], status_code=201)
async def ghana_card(
    db: DB,
    user: Lister,
    card_number: Annotated[str, Form(examples=["GHA-712345678-3"])],
    full_name: Annotated[str, Form(min_length=2, max_length=160)],
    selfie: UploadFile | None = None,
):
    """Check a Ghana Card with the KYC provider. The selfie is used for the liveness check
    and is not stored by Afe."""
    selfie_bytes = await read_upload(selfie, MAX_PHOTO_BYTES) if selfie else None
    return ok(s.IdentityCheckOut.model_validate(check_ghana_card(db, user, card_number, full_name, selfie_bytes)))


@router.get("/ghana-card", response_model=Envelope[s.IdentityCheckOut | None])
def my_ghana_card(db: DB, user: Lister):
    check = latest_check(db, user)
    return ok(s.IdentityCheckOut.model_validate(check) if check else None)


@router.post("/units/{unit_id}/authority", response_model=Envelope[s.AuthorityOut], status_code=201)
async def upload_authority(
    db: DB,
    user: Lister,
    unit_id: int,
    relationship: Annotated[str, Form()],
    document_type: Annotated[str, Form()],
    document: UploadFile,
    utility_reference: Annotated[str, Form(max_length=40)] = "",
):
    unit = get_or_404(db, Unit, unit_id, "Home")
    if unit.registered_by_id != user.id:
        raise NotAllowed("Upload documents for homes you registered.")
    data = await read_upload(document, units.MAX_DOCUMENT_BYTES)
    with keep_attempts(db):
        record = units.add_authority(db, user, unit, relationship, document_type, data, utility_reference)
    return ok(s.AuthorityOut.model_validate(record))
