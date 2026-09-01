"""POST /api/simulate — the same index calculation re-run with adjusted inputs.

The three request fields are the three sliders in features.md F6.
"""

from pydantic import BaseModel, Field

from api.schemas.common import Contribution, FactorScores


class SimulateRequest(BaseModel):
    destination_id: int
    expected_tourists: int = Field(ge=0)
    waste_management_level: int = Field(ge=0, le=100)
    infrastructure_level: int = Field(ge=0, le=100)


class SimulateData(BaseModel):
    destination_id: int
    baseline_score: int = Field(ge=0, le=100)
    sustainability_score: int = Field(ge=0, le=100)
    factors: FactorScores
    contributions: list[Contribution]
    # Set when the change drops the score by more than 10 points.
    warning: str | None = None
