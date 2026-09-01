"""POST /api/recommend.

Mock data only. The real Sustainability Index lands on a later branch; the
shape here is what the frontend builds against until then.
"""

from typing import Any

from fastapi import APIRouter

from api.envelope import envelope
from api.schemas.common import Envelope
from api.schemas.recommend import RecommendData, RecommendRequest

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=Envelope[RecommendData])
def recommend(request: RecommendRequest) -> dict[str, Any]:
    data = RecommendData(
        results=[
            {
                "destination_id": 7,
                "name": "Belihuloya",
                "sustainability_score": 89,
                "factors": {
                    "environmental": 92,
                    "community": 88,
                    "crowd": 91,
                    "infrastructure": 76,
                    "suitability": 90,
                },
                "contributions": [
                    {"factor": "environmental", "percent": 32, "type": "exact"},
                    {"factor": "crowd", "percent": 25, "type": "exact"},
                    {"factor": "community", "percent": 20, "type": "exact"},
                    {"factor": "suitability", "percent": 15, "type": "exact"},
                    {"factor": "infrastructure", "percent": 8, "type": "exact"},
                ],
                "explanation": (
                    "Recommended mainly because of low visitor pressure and "
                    "strong environmental conditions."
                ),
                "confidence": "measured",
            },
            {
                "destination_id": 12,
                "name": "Meemure",
                "sustainability_score": 84,
                "factors": {
                    "environmental": 90,
                    "community": 86,
                    "crowd": 94,
                    "infrastructure": 58,
                    "suitability": 82,
                },
                "contributions": [
                    {"factor": "crowd", "percent": 30, "type": "exact"},
                    {"factor": "environmental", "percent": 28, "type": "exact"},
                    {"factor": "community", "percent": 22, "type": "exact"},
                    {"factor": "suitability", "percent": 14, "type": "exact"},
                    {"factor": "infrastructure", "percent": 6, "type": "exact"},
                ],
                "explanation": (
                    "Ranked below Belihuloya mainly because of infrastructure."
                ),
                "confidence": "estimated",
            },
        ]
    )
    return envelope(data)
