from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, RuleViolation, UploadRejected
from app.core.geo import coord
from app.core.ghana import normalise_digital_address, normalise_phone
from app.db import utcnow
from app.modules.audit.log import record
from app.modules.detection.hooks import enqueue, label
from app.modules.media.storage import storage

from .models import AuthorityRecord, AuthorityStatus, DocumentType, PropertyType, Relationship, Unit

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_TYPES = {b"%PDF": ".pdf", b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png"}


def register_unit(
    db: Session,
    actor,
    area,
    digital_address: str,
    unit_label: str,
    lat,
    lng,
    property_type: str,
    bedrooms: int,
    bathrooms: int = 1,
    landmark: str = "",
) -> Unit:
    """Register a home once. The same address and unit label can never be registered twice."""
    if not area.is_active:
        raise RuleViolation(f"Afe is not open in {area.name} yet.")
    if not area.contains(lat, lng):
        raise InvalidInput(f"The map pin is outside {area.name}.")
    if property_type not in PropertyType.__members__.values():
        raise InvalidInput("Choose a property type.")
    unit = Unit(
        area_id=area.id,
        digital_address=normalise_digital_address(digital_address),
        unit_label=(unit_label or "Whole property").strip(),
        lat=coord(lat),
        lng=coord(lng),
        property_type=property_type,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        landmark=landmark,
        registered_by_id=actor.id,
    )
    db.add(unit)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise RuleViolation("This home is already registered on Afe.") from exc
    record(db, actor, "unit.registered", unit)
    return unit


def _scan_or_refuse(db: Session, actor, unit: Unit, document: bytes) -> None:
    """Refuse infected or unscannable files before they reach storage (fail closed)."""
    from app.modules.media.scan import ScanUnavailable, get_scanner
    from app.modules.risk.flags import raise_flag
    from app.modules.risk.models import Severity

    try:
        result = get_scanner().scan(document)
    except ScanUnavailable as exc:
        raise InvalidInput("We couldn't check this file for viruses just now. Try again in a few minutes.") from exc
    if not result.clean:
        record(db, actor, "upload.malware_refused", unit, signature=result.signature)
        raise_flag(db, actor, "upload.malware", Severity.HIGH,
                   f"Uploaded a document containing malware ({result.signature})", unit=unit.id)
        raise UploadRejected("This file can't be accepted: our virus check found a problem with it. "
                             "Upload a fresh scan or photo of the document.")


def add_authority(
    db: Session, actor, unit: Unit, relationship: str, document_type: str, document: bytes, utility_reference: str = ""
) -> AuthorityRecord:
    """Store an ownership or authorisation document in the private store."""
    if not actor.is_lister:
        raise NotAllowed("Only landlords and agents can upload authority documents.")
    if relationship not in Relationship.__members__.values() or document_type not in DocumentType.__members__.values():
        raise InvalidInput("Choose the relationship and document type.")
    if len(document) > MAX_DOCUMENT_BYTES:
        raise InvalidInput("Document is larger than 10 MB.")
    suffix = next((ext for magic, ext in DOCUMENT_TYPES.items() if document.startswith(magic)), None)
    if suffix is None:
        raise InvalidInput("Upload the document as a PDF, JPEG or PNG.")
    _scan_or_refuse(db, actor, unit, document)
    key = storage.save("private", "authority", document, suffix)
    authority = AuthorityRecord(
        unit_id=unit.id,
        party_id=actor.id,
        relationship_type=relationship,
        document_type=document_type,
        document_key=key,
        utility_reference=utility_reference,
    )
    db.add(authority)
    db.flush()
    record(db, actor, "authority.uploaded", authority)
    enqueue(db, "documents", authority)
    return authority


def confirm_owner_by_phone(db: Session, authority: AuthorityRecord, staff, owner_phone: str, owner_name: str):
    """Record that Afe called the owner on a number it found itself and the owner confirmed."""
    if not (staff.can_review or staff.role == "field_verifier"):
        raise NotAllowed("Only Afe staff can record an owner callback.")
    authority.owner_phone = normalise_phone(owner_phone)
    authority.owner_name = owner_name
    authority.owner_confirmed_at = utcnow()
    authority.owner_confirmed_by_id = staff.id
    db.flush()
    record(db, staff, "authority.owner_confirmed", authority)
    return authority


def review_authority(db: Session, authority: AuthorityRecord, reviewer, accept: bool, note: str = ""):
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can accept authority documents.")
    if accept and authority.needs_owner_callback and not authority.owner_confirmed_at:
        raise RuleViolation("An agent or caretaker needs the owner confirmed by phone first.")
    if (
        accept
        and authority.relationship_type == Relationship.OWNER
        and authority.document_type == DocumentType.OWNER_AUTHORISATION
    ):
        raise RuleViolation("An owner must provide an ownership document, not an authorisation letter.")
    authority.status = AuthorityStatus.ACCEPTED if accept else AuthorityStatus.REJECTED
    authority.reviewed_by_id = reviewer.id
    authority.reviewed_at = utcnow()
    authority.review_note = note
    db.flush()
    record(db, reviewer, "authority.reviewed", authority, status=authority.status, note=note)
    if accept:
        label(db, authority, fraud=False, source="authority", decided_by=reviewer)
    return authority


def has_authority(db: Session, party, unit) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    AuthorityRecord.party_id == party.id,
                    AuthorityRecord.unit_id == unit.id,
                    AuthorityRecord.status == AuthorityStatus.ACCEPTED,
                )
            )
        )
    )


def accepted_authority(db: Session, party, unit) -> AuthorityRecord | None:
    return db.scalar(
        select(AuthorityRecord).where(
            AuthorityRecord.party_id == party.id,
            AuthorityRecord.unit_id == unit.id,
            AuthorityRecord.status == AuthorityStatus.ACCEPTED,
        )
    )
