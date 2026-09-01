"""index_weights (plan.md section 8).

config/weights.yaml stays the source of truth for the running index. This table
records which weights produced a score that was already shown to a user.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class IndexWeight(Base):
    __tablename__ = "index_weights"

    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    factor: Mapped[str] = mapped_column(String(40), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
