from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.geo import distance_m
from app.db import Base, TimestampMixin, utcnow
from app.modules.accounts.models import User
from app.modules.identity.models import IdentityCheck
from app.modules.units.models import Coordinate, Unit


class ReasonCode(StrEnum):
    """Fixed list so every decision doubles as a clean training label (plan §7)."""

    # Approval evidence
    ID_MATCH = "ID_MATCH"
    ID_SEEN_IN_PERSON = "ID_SEEN_IN_PERSON"
    DOCS_SIGHTED = "DOCS_SIGHTED"
    OWNER_CONFIRMED = "OWNER_CONFIRMED"
    VISIT_MATCH = "VISIT_MATCH"
    # Rejection reasons
    ID_MISMATCH = "ID_MISMATCH"
    DOCS_MISSING = "DOCS_MISSING"
    DOCS_SUSPECT = "DOCS_SUSPECT"
    OWNER_UNREACHABLE = "OWNER_UNREACHABLE"
    OWNER_DENIES = "OWNER_DENIES"
    UNIT_NOT_FOUND = "UNIT_NOT_FOUND"
    UNIT_OCCUPIED = "UNIT_OCCUPIED"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    DUPLICATE_PHOTOS = "DUPLICATE_PHOTOS"
    DUPLICATE_ACCOUNT = "DUPLICATE_ACCOUNT"
    FRAUD_REPORT = "FRAUD_REPORT"
    OTHER = "OTHER"


REASON_LABELS = {
    ReasonCode.ID_MATCH: "Ghana Card checked and name matches",
    ReasonCode.ID_SEEN_IN_PERSON: "Ghana Card seen in person at the visit",
    ReasonCode.DOCS_SIGHTED: "Ownership or authority documents sighted",
    ReasonCode.OWNER_CONFIRMED: "Owner confirmed by phone",
    ReasonCode.VISIT_MATCH: "Unit exists and matches the listing",
    ReasonCode.ID_MISMATCH: "Identity does not match",
    ReasonCode.DOCS_MISSING: "Documents missing",
    ReasonCode.DOCS_SUSPECT: "Documents look altered",
    ReasonCode.OWNER_UNREACHABLE: "Owner could not be reached",
    ReasonCode.OWNER_DENIES: "Owner denies giving authority",
    ReasonCode.UNIT_NOT_FOUND: "Unit not found at the address",
    ReasonCode.UNIT_OCCUPIED: "Unit is occupied",
    ReasonCode.UNIT_MISMATCH: "Unit does not match what was described",
    ReasonCode.DUPLICATE_PHOTOS: "Photos match another property",
    ReasonCode.DUPLICATE_ACCOUNT: "Same person on another account",
    ReasonCode.FRAUD_REPORT: "Upheld fraud report",
    ReasonCode.OTHER: "Other (see note)",
}
APPROVAL_CODES = {
    ReasonCode.ID_MATCH,
    ReasonCode.ID_SEEN_IN_PERSON,
    ReasonCode.DOCS_SIGHTED,
    ReasonCode.OWNER_CONFIRMED,
    ReasonCode.VISIT_MATCH,
}


class VisitOutcome(StrEnum):
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"


PHOTO_CAPTIONS = [
    "Living room",
    "Bedroom",
    "Kitchen",
    "Bathroom",
    "Toilet",
    "Compound",
    "Entrance or gate",
    "ECG meter",
    "Street view",
    "Other",
]

CHECKLIST_ITEMS = {
    "met_landlord_or_caretaker": "Met the landlord or caretaker",
    "ghana_card_seen_in_person": "Saw the Ghana Card in person, and it matches",
    "unit_exists": "Unit exists at the digital address",
    "unit_vacant": "Unit is vacant or will be by the move-in date",
    "matches_description": "Rooms, bathrooms and condition match the listing",
}


class AssignmentStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class VisitAssignment(TimestampMixin, Base):
    """A reviewer sends a verifier to a home. Verifiers visit only homes assigned to them,
    so no one can pick which landlords they verify (plan §5, controls on verifiers)."""

    __tablename__ = "visit_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    verifier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scheduled_for: Mapped[date]
    note: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default=AssignmentStatus.OPEN, index=True)
    # "verification", or "qa_recheck": an unannounced second visit by a different verifier (plan §5).
    purpose: Mapped[str] = mapped_column(String(12), default="verification", server_default="verification")
    rechecks_visit_id: Mapped[int | None] = mapped_column(ForeignKey("field_visits.id", use_alter=True))

    unit: Mapped[Unit] = relationship()
    verifier: Mapped[User] = relationship(foreign_keys=[verifier_id])


class FieldVisit(TimestampMixin, Base):
    """An Afe field verifier's visit to a unit (plan §5, step 3)."""

    __tablename__ = "field_visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    verifier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("visit_assignments.id"))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None]
    checkin_lat: Mapped[Decimal] = mapped_column(Coordinate)
    checkin_lng: Mapped[Decimal] = mapped_column(Coordinate)
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(12), default=VisitOutcome.IN_PROGRESS)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Logged by the verifier at the end of a visit, for the cost of a verification (plan §5).
    travel_minutes: Mapped[int | None]
    transport_pesewas: Mapped[int | None]

    unit: Mapped[Unit] = relationship()
    verifier: Mapped[User] = relationship()
    photos: Mapped[list["VisitPhoto"]] = relationship(back_populates="visit", order_by="VisitPhoto.taken_at")

    @property
    def checkin_distance_m(self) -> float:
        return distance_m((float(self.checkin_lat), float(self.checkin_lng)), self.unit.point)


class VisitPhoto(Base):
    """A photo taken by Afe during a field visit. The only photos a verified listing shows."""

    __tablename__ = "visit_photos"
    __table_args__ = (UniqueConstraint("visit_id", "client_ref", name="visit_photo_client_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("field_visits.id"), index=True)
    client_ref: Mapped[str | None] = mapped_column(
        String(64), comment="Set by the phone; a retried upload returns the photo already saved"
    )
    image_key: Mapped[str] = mapped_column(String(200), comment="Key in the public media store")
    width: Mapped[int]
    height: Mapped[int]
    caption: Mapped[str] = mapped_column(String(80), default="")
    taken_at: Mapped[datetime]
    lat: Mapped[Decimal] = mapped_column(Coordinate)
    lng: Mapped[Decimal] = mapped_column(Coordinate)
    phash: Mapped[str] = mapped_column(String(16), index=True)
    dhash: Mapped[str] = mapped_column(String(16))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("visit_photos.id", ondelete="SET NULL"))

    visit: Mapped[FieldVisit] = relationship(back_populates="photos")
    duplicate_of: Mapped["VisitPhoto | None"] = relationship(remote_side=[id])


class VerificationStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class Verification(Base):
    """A reviewer's decision about a person or a unit. A badge shows only while the latest
    decision is approved, unexpired and unrevoked. Never edited: a new decision is a new row."""

    __tablename__ = "verifications"
    __table_args__ = (
        CheckConstraint(
            "(party_id IS NOT NULL AND unit_id IS NULL) OR (party_id IS NULL AND unit_id IS NOT NULL)",
            name="has_one_subject",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    status: Mapped[str] = mapped_column(String(10))
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(String(300), default="")
    identity_check_id: Mapped[int | None] = mapped_column(ForeignKey("identity_checks.id"))
    field_visit_id: Mapped[int | None] = mapped_column(ForeignKey("field_visits.id"))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(default=utcnow)
    expiry_reminded_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    party: Mapped[User | None] = relationship(foreign_keys=[party_id])
    unit: Mapped[Unit | None] = relationship()
    identity_check: Mapped[IdentityCheck | None] = relationship()
    field_visit: Mapped[FieldVisit | None] = relationship()
    decided_by: Mapped[User] = relationship(foreign_keys=[decided_by_id])

    @property
    def is_current(self) -> bool:
        return self.status == VerificationStatus.APPROVED and self.expires_at is not None and self.expires_at > utcnow()
