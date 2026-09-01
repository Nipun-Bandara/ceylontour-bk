"""POST /api/recommend — field names taken verbatim from plan.md section 7."""

from pydantic import BaseModel, Field

from api.schemas.common import Confidence, Contribution, FactorScores, Meta


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


class ExclusionSummary(BaseModel):
    """Why destinations did not make the list.

    Budget and duration are filters, not scored factors: a destination that
    does not fit is excluded rather than penalised (features.md F2). Reporting
    the counts is what keeps "every destination gets scored, no silent drops"
    checkable from the outside.
    """

    # Distinct destinations excluded. The reasons below can overlap, so they
    # may add up to more than this.
    total: int = Field(ge=0)
    over_budget: int = Field(ge=0)
    over_duration: int = Field(ge=0)
    # A destination with no row in destination_factors cannot be scored.
    # Counted rather than dropped quietly.
    missing_factors: int = Field(ge=0)


class RecommendMeta(Meta):
    """Meta for this endpoint only. Every other route still returns plain Meta,
    so the shared envelope shape is unchanged.
    """

    excluded: ExclusionSummary


class RecommendEnvelope(BaseModel):
    data: RecommendData
    meta: RecommendMeta
