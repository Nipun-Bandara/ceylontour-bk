"""GET /api/destinations and GET /api/destinations/{id}.

Fields follow the destinations table in plan.md section 8, plus the current
pressure band the map colours its markers by (features.md F7).
"""

from pydantic import BaseModel, Field

from api.schemas.common import Band, Confidence, FactorScores


class DestinationSummary(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    district: str
    region: str
    landscape_type: str
    cost_band: str
    typical_days: int
    band: Band


class DestinationListData(BaseModel):
    destinations: list[DestinationSummary]


class DestinationDetail(DestinationSummary):
    activities: list[str]
    sustainability_score: int = Field(ge=0, le=100)
    factors: FactorScores
    confidence: Confidence
