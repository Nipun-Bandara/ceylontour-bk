"""GET /api/dashboard/summary. Mock data only.

The contract marks this endpoint as auth required. The JWT check is not built
on this branch, so the route is open for now.
"""

from typing import Any

from fastapi import APIRouter

from api.envelope import envelope
from api.schemas.common import Envelope
from api.schemas.dashboard import DashboardSummaryData

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=Envelope[DashboardSummaryData])
def get_summary() -> dict[str, Any]:
    data = DashboardSummaryData(
        destinations_monitored=17,
        band_counts={"low": 9, "medium": 5, "high": 3},
        highest_pressure=[
            {
                "destination_id": 3,
                "name": "Ella",
                "region": "Uva",
                "predicted_pressure": 81.2,
                "band": "high",
            },
            {
                "destination_id": 1,
                "name": "Sigiriya",
                "region": "Central",
                "predicted_pressure": 77.5,
                "band": "high",
            },
        ],
        recommended_action=(
            "Three destinations are in the high band for this month. Consider "
            "promoting lower-pressure alternatives in the same regions."
        ),
        global_feature_importance=[
            {"feature": "month", "importance": 0.41},
            {"feature": "recent_occupancy", "importance": 0.27},
            {"feature": "arrival_trend", "importance": 0.18},
            {"feature": "holiday_indicator", "importance": 0.14},
        ],
    )
    return envelope(data)
