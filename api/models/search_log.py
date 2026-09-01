"""search_log (plan.md section 8).

Stores what was asked and what was returned, so a recommendation shown in the
demo can be reproduced afterwards.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class SearchLog(Base):
    __tablename__ = "search_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    results_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Null until the user picks something.
    accepted_destination_id: Mapped[int | None] = mapped_column(
        ForeignKey("destinations.id", ondelete="SET NULL"), nullable=True
    )
