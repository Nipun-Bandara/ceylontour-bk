"""GET /api/risk/{id}?month= — pressure forecast, band and SHAP breakdown."""

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.common import Band, Contribution


class RiskData(BaseModel):
    destination_id: int
    region: str
    month: int = Field(ge=1, le=12)
    predicted_pressure: float = Field(ge=0, le=100)
    band: Band
    # SLTDA data is regional, so the forecast cannot be claimed as per-site.
    # Carried in the response so the UI cannot forget to say it (features.md F4).
    scope: Literal["regional"] = "regional"
    # Always type "estimated"; these are SHAP values, not exact contributions.
    contributions: list[Contribution]
