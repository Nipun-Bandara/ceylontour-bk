"""GET /api/alternatives/{id} — similar destinations with lower pressure."""

from pydantic import BaseModel, Field

from api.schemas.common import Band


class Alternative(BaseModel):
    destination_id: int
    name: str
    similarity_percent: int = Field(ge=0, le=100)
    predicted_pressure: float = Field(ge=0, le=100)
    band: Band
    reason: str


class AlternativesData(BaseModel):
    destination_id: int
    alternatives: list[Alternative]
    # Set when no similar lower-pressure destination exists, so the UI can say
    # so instead of showing a bad match (features.md F5).
    message: str | None = None
