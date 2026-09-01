"""POST /api/simulate. Mock data only.

The real version re-runs the same index calculation with the adjusted inputs.
Nothing is recomputed here.
"""

from typing import Any

from fastapi import APIRouter

from api.envelope import envelope
from api.schemas.common import Envelope
from api.schemas.simulate import SimulateData, SimulateRequest

router = APIRouter(prefix="/api", tags=["simulate"])


@router.post("/simulate", response_model=Envelope[SimulateData])
def simulate(request: SimulateRequest) -> dict[str, Any]:
    data = SimulateData(
        destination_id=request.destination_id,
        baseline_score=89,
        sustainability_score=74,
        factors={
            "environmental": 78,
            "community": 88,
            "crowd": 62,
            "infrastructure": 70,
            "suitability": 90,
        },
        contributions=[
            {"factor": "environmental", "percent": 30, "type": "exact"},
            {"factor": "crowd", "percent": 25, "type": "exact"},
            {"factor": "community", "percent": 20, "type": "exact"},
            {"factor": "suitability", "percent": 15, "type": "exact"},
            {"factor": "infrastructure", "percent": 10, "type": "exact"},
        ],
        warning=(
            "This combination lowers the sustainability score by 15 points."
        ),
    )
    return envelope(data)
