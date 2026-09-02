"""POST /api/simulate — the same index calculation re-run with adjusted inputs.

The three request fields are the three sliders in features.md F6.
"""

from pydantic import BaseModel, Field

from api.schemas.common import Contribution, FactorScores


class SimulateRequest(BaseModel):
    destination_id: int
    # All three are slider positions, 0 to 100, not real-world quantities.
    # expected_tourists is "how busy", not a headcount.
    expected_tourists: int = Field(ge=0, le=100)
    waste_management_level: int = Field(ge=0, le=100)
    infrastructure_level: int = Field(ge=0, le=100)


class SimulateData(BaseModel):
    destination_id: int
    # The destination as it stands today, so the UI has something to compare
    # against and can show what the sliders changed.
    baseline_score: int = Field(ge=0, le=100)
    sustainability_score: int = Field(ge=0, le=100)
    # sustainability_score - baseline_score. Negative means the change made
    # things worse.
    delta: int = Field(ge=-100, le=100)
    factors: FactorScores
    contributions: list[Contribution]
    # Set when the change drops the score by more than 10 points (F6).
    warning: str | None = None
