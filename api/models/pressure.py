"""region_pressure_history and pressure_forecast (plan.md section 8)."""

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class RegionPressureHistory(Base):
    """SLTDA monthly series, the training data for the pressure model.

    The natural key is region + year + month, so that is the primary key
    rather than an invented id column.
    """

    __tablename__ = "region_pressure_history"

    region: Mapped[str] = mapped_column(String(80), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    occupancy_rate: Mapped[float] = mapped_column(Float, nullable=False)
    arrivals: Mapped[int] = mapped_column(Integer, nullable=False)
    guest_nights: Mapped[int] = mapped_column(Integer, nullable=False)


class PressureForecast(Base):
    """Model output. Keyed by model_version too, so an old prediction stays
    reproducible after the model is retrained.
    """

    __tablename__ = "pressure_forecast"

    region: Mapped[str] = mapped_column(String(80), primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    predicted_pressure: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String(20), nullable=False)
