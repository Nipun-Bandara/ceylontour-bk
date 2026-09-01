"""GET /api/destinations and GET /api/destinations/{id}. Mock data only."""

from typing import Any

from fastapi import APIRouter

from api.envelope import envelope
from api.schemas.common import Envelope
from api.schemas.destinations import DestinationDetail, DestinationListData

router = APIRouter(prefix="/api/destinations", tags=["destinations"])

_MOCK_DESTINATIONS = [
    {
        "id": 7,
        "name": "Belihuloya",
        "lat": 6.7167,
        "lon": 80.7833,
        "district": "Ratnapura",
        "region": "Sabaragamuwa",
        "landscape_type": "mountain",
        "cost_band": "low",
        "typical_days": 3,
        "band": "low",
    },
    {
        "id": 12,
        "name": "Meemure",
        "lat": 7.3833,
        "lon": 80.8333,
        "district": "Kandy",
        "region": "Central",
        "landscape_type": "forest",
        "cost_band": "low",
        "typical_days": 2,
        "band": "low",
    },
    {
        "id": 3,
        "name": "Ella",
        "lat": 6.8667,
        "lon": 81.0466,
        "district": "Badulla",
        "region": "Uva",
        "landscape_type": "mountain",
        "cost_band": "medium",
        "typical_days": 4,
        "band": "high",
    },
]


@router.get("", response_model=Envelope[DestinationListData])
def list_destinations() -> dict[str, Any]:
    return envelope(DestinationListData(destinations=_MOCK_DESTINATIONS))


@router.get("/{destination_id}", response_model=Envelope[DestinationDetail])
def get_destination(destination_id: int) -> dict[str, Any]:
    data = DestinationDetail(
        **_MOCK_DESTINATIONS[0],
        activities=["hiking", "waterfalls", "cycling"],
        sustainability_score=89,
        factors={
            "environmental": 92,
            "community": 88,
            "crowd": 91,
            "infrastructure": 76,
            "suitability": 90,
        },
        confidence="measured",
    )
    # The path id is echoed back so the mock still looks consistent to the
    # frontend whichever destination it asks for.
    data.id = destination_id
    return envelope(data)
