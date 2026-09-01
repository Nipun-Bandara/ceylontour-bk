"""destinations and destination_factors (plan.md section 8)."""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base


class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Plain columns, no PostGIS. 15 to 20 fixed markers do not need it
    # (plan.md section 9, cut 2).
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    district: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    landscape_type: Mapped[str] = mapped_column(String(80), nullable=False)
    activities: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    cost_band: Mapped[str] = mapped_column(String(40), nullable=False)
    typical_days: Mapped[int] = mapped_column(Integer, nullable=False)

    factors: Mapped["DestinationFactor | None"] = relationship(
        back_populates="destination", uselist=False
    )


class DestinationFactor(Base):
    """One row per destination: the five factor values behind its score.

    source_ref and confidence are not optional. They are the answer when a
    judge asks where a number came from (plan.md section 8).
    """

    __tablename__ = "destination_factors"

    destination_id: Mapped[int] = mapped_column(
        ForeignKey("destinations.id", ondelete="CASCADE"), primary_key=True
    )
    environmental: Mapped[float] = mapped_column(Float, nullable=False)
    community: Mapped[float] = mapped_column(Float, nullable=False)
    crowd: Mapped[float] = mapped_column(Float, nullable=False)
    infrastructure: Mapped[float] = mapped_column(Float, nullable=False)
    suitability: Mapped[float] = mapped_column(Float, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)

    destination: Mapped[Destination] = relationship(back_populates="factors")
