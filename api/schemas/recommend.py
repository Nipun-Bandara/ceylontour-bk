"""POST /api/recommend — field names taken verbatim from plan.md section 7."""

from pydantic import BaseModel, Field

from api.schemas.common import Confidence, Contribution, FactorScores


class RecommendRequest(BaseModel):
    budget_lkr: int = Field(ge=0)
    duration_days: int = Field(ge=1)
    interest: str
    # Left as free strings on purpose; the allowed values are decided by the
    # dataset, not by this branch.
    crowd_preference: str
    sustainability_weight: str
    travel_month: int = Field(ge=1, le=12)


class Recommendation(BaseModel):
    destination_id: int
    name: str
    sustainability_score: int = Field(ge=0, le=100)
    factors: FactorScores
    contributions: list[Contribution]
    explanation: str
    confidence: Confidence


class RecommendData(BaseModel):
    results: list[Recommendation]
