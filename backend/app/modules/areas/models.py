from datetime import date
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.geo import polygon_contains
from app.db import Base, TimestampMixin


class ServiceArea(TimestampMixin, Base):
    """A neighbourhood Afe covers. Areas are switched on one at a time (plan §17)."""

    __tablename__ = "service_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    country: Mapped[str] = mapped_column(String(2), default="GH")
    city: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    is_active: Mapped[bool] = mapped_column(default=False)
    boundary: Mapped[list] = mapped_column(JSON, comment="Polygon as a list of [lat, lng] points")

    price_bands: Mapped[list["PriceBand"]] = relationship(back_populates="area", order_by="PriceBand.as_of.desc()")

    def contains(self, lat, lng) -> bool:
        return polygon_contains([tuple(p) for p in self.boundary], (float(lat), float(lng)))


class PriceSource(StrEnum):
    SURVEY = "survey"
    LISTINGS = "listings"


class PriceBand(TimestampMixin, Base):
    """Monthly rent range for an area and bedroom count. Seeded from the manual rent survey."""

    __tablename__ = "price_bands"

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id", ondelete="CASCADE"))
    bedrooms: Mapped[int] = mapped_column(comment="0 = single room / chamber and hall")
    low_pesewas: Mapped[int]
    median_pesewas: Mapped[int]
    high_pesewas: Mapped[int]
    source: Mapped[str] = mapped_column(String(10), default=PriceSource.SURVEY)
    as_of: Mapped[date]

    area: Mapped[ServiceArea] = relationship(back_populates="price_bands")
