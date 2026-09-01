"""GET /api/alternatives/{id}. Mock data only."""

from typing import Any

from fastapi import APIRouter

from api.envelope import envelope
from api.schemas.alternatives import AlternativesData
from api.schemas.common import Envelope

router = APIRouter(prefix="/api/alternatives", tags=["alternatives"])


@router.get("/{destination_id}", response_model=Envelope[AlternativesData])
def get_alternatives(destination_id: int) -> dict[str, Any]:
    data = AlternativesData(
        destination_id=destination_id,
        alternatives=[
            {
                "destination_id": 7,
                "name": "Belihuloya",
                "similarity_percent": 87,
                "predicted_pressure": 38.4,
                "band": "low",
                "reason": "Similar mountain landscape with far lower visitor pressure.",
            },
            {
                "destination_id": 12,
                "name": "Meemure",
                "similarity_percent": 79,
                "predicted_pressure": 21.7,
                "band": "low",
                "reason": "Comparable hiking activities and a quieter month ahead.",
            },
            {
                "destination_id": 15,
                "name": "Riverston",
                "similarity_percent": 74,
                "predicted_pressure": 44.9,
                "band": "medium",
                "reason": "Same climate band and viewpoints, with fewer visitors.",
            },
        ],
    )
    return envelope(data)
