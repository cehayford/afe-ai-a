from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin
from app.modules.accounts.models import User
from app.modules.areas.models import ServiceArea

Coordinate = Numeric(9, 6)


class PropertyType(StrEnum):
    SINGLE_ROOM = "single_room"
    CHAMBER_AND_HALL = "chamber_and_hall"
    SELF_CONTAINED = "self_contained"
    APARTMENT = "apartment"
    HOUSE = "house"


PROPERTY_TYPE_LABELS = {
    PropertyType.SINGLE_ROOM: "Single room",
    PropertyType.CHAMBER_AND_HALL: "Chamber and hall",
    PropertyType.SELF_CONTAINED: "Self-contained",
    PropertyType.APARTMENT: "Apartment",
    PropertyType.HOUSE: "House",
}


class Unit(TimestampMixin, Base):
    """One physical home. Registered once; every listing is an offer on a unit (plan §3)."""

    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("digital_address", "unit_label", name="unit_unique_per_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id"), index=True)
    digital_address: Mapped[str] = mapped_column(String(14), comment="GhanaPost GPS, e.g. GA-183-8164")
    unit_label: Mapped[str] = mapped_column(String(40), default="Whole property")
    lat: Mapped[Decimal] = mapped_column(Coordinate)
    lng: Mapped[Decimal] = mapped_column(Coordinate)
    property_type: Mapped[str] = mapped_column(String(20))
    bedrooms: Mapped[int] = mapped_column(comment="0 for a single room or chamber and hall")
    bathrooms: Mapped[int] = mapped_column(default=1)
    landmark: Mapped[str] = mapped_column(String(160), default="")
    registered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    area: Mapped[ServiceArea] = relationship()
    registered_by: Mapped[User] = relationship()
    authority_records: Mapped[list["AuthorityRecord"]] = relationship(
        back_populates="unit", order_by="AuthorityRecord.id"
    )

    @property
    def point(self) -> tuple[float, float]:
        return float(self.lat), float(self.lng)

    @property
    def property_type_label(self) -> str:
        return PROPERTY_TYPE_LABELS[PropertyType(self.property_type)]

    def __str__(self) -> str:
        return f"{self.digital_address} · {self.unit_label}"


class Relationship(StrEnum):
    OWNER = "owner"
    AUTHORISED_AGENT = "authorised_agent"
    CARETAKER = "caretaker"


class DocumentType(StrEnum):
    LAND_TITLE = "land_title"
    INDENTURE = "indenture"
    LANDS_COMMISSION_SEARCH = "lands_commission_search"
    SITE_PLAN = "site_plan"
    OWNER_AUTHORISATION = "owner_authorisation"


DOCUMENT_LABELS = {
    DocumentType.LAND_TITLE: "Land title certificate",
    DocumentType.INDENTURE: "Indenture",
    DocumentType.LANDS_COMMISSION_SEARCH: "Lands Commission search report",
    DocumentType.SITE_PLAN: "Site plan",
    DocumentType.OWNER_AUTHORISATION: "Signed owner authorisation",
}
RELATIONSHIP_LABELS = {
    Relationship.OWNER: "Owner",
    Relationship.AUTHORISED_AGENT: "Agent authorised by the owner",
    Relationship.CARETAKER: "Caretaker authorised by the owner",
}


class AuthorityStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AuthorityRecord(TimestampMixin, Base):
    """Proof that a person may let a unit: the owner's document, or an owner's signed
    authorisation for an agent, confirmed by calling the owner (plan §5, step 2)."""

    __tablename__ = "authority_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    relationship_type: Mapped[str] = mapped_column("relationship", String(20))
    document_type: Mapped[str] = mapped_column(String(30))
    document_key: Mapped[str] = mapped_column(String(200), comment="Key in the private (KYC) store")
    utility_reference: Mapped[str] = mapped_column(String(40), default="", comment="ECG meter or utility account")
    owner_name: Mapped[str] = mapped_column(String(160), default="")
    owner_phone: Mapped[str] = mapped_column(String(16), default="", comment="Found by Afe, not given by the agent")
    owner_confirmed_at: Mapped[datetime | None]
    owner_confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(10), default=AuthorityStatus.PENDING)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str] = mapped_column(String(300), default="")

    unit: Mapped[Unit] = relationship(back_populates="authority_records")
    party: Mapped[User] = relationship(foreign_keys=[party_id])

    @property
    def needs_owner_callback(self) -> bool:
        return self.relationship_type != Relationship.OWNER

    @property
    def document_label(self) -> str:
        return DOCUMENT_LABELS[DocumentType(self.document_type)]

    @property
    def relationship_label(self) -> str:
        return RELATIONSHIP_LABELS[Relationship(self.relationship_type)]
