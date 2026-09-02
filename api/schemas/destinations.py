"""GET /api/destinations and GET /api/destinations/{id}.

Fields follow the destinations table in plan.md section 8. The list is what
the map needs to place and colour a marker; the detail is what the panel
needs once a marker is clicked (features.md F7).
"""

from pydantic import BaseModel, Field

from api.schemas.common import Band, Confidence, FactorScores


class DestinationSummary(BaseModel):
    """Enough to draw one marker: where it is, and what colour it is."""

    id: int
    name: str
    lat: float
    lon: float
    district: str
    region: str
    sustainability_score: int = Field(ge=0, le=100)
    # Visitor pressure for this destination's region, this month. The same
    # band /api/risk reports, from the same config thresholds.
    band: Band


class DestinationListData(BaseModel):
    destinations: list[DestinationSummary]


class DestinationDetail(DestinationSummary):
    """Everything the marker panel shows."""

    factors: FactorScores
    confidence: Confidence
    activities: list[str]
    cost_band: str
    typical_days: int
    # Where the factor values came from. Shown so a reader can check a number
    # rather than taking it on trust (plan.md section 8).
    source_ref: str
