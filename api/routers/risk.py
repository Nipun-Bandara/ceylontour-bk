"""GET /api/risk/{id}?month=. Mock data only.

The contributions here stand in for TreeSHAP output, so every one of them is
type "estimated" rather than "exact".
"""

from typing import Any

from fastapi import APIRouter, Query

from api.envelope import envelope
from api.schemas.common import Envelope
from api.schemas.risk import RiskData

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/{destination_id}", response_model=Envelope[RiskData])
def get_risk(
    destination_id: int,
    month: int = Query(ge=1, le=12),
) -> dict[str, Any]:
    data = RiskData(
        destination_id=destination_id,
        region="Sabaragamuwa",
        month=month,
        predicted_pressure=38.4,
        band="low",
        contributions=[
            {"factor": "month", "percent": 41, "type": "estimated"},
            {"factor": "recent_occupancy", "percent": 27, "type": "estimated"},
            {"factor": "arrival_trend", "percent": 18, "type": "estimated"},
            {"factor": "holiday_indicator", "percent": 14, "type": "estimated"},
        ],
    )
    return envelope(data)
