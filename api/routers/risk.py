"""GET /api/risk/{id}?month=.

Real forecasts now. The destination decides which region is asked about; the
pressure figure itself is regional, which the response says in as many words.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope
from api.models import Destination
from api.schemas.common import Envelope, Meta
from api.schemas.risk import RiskData
from api.services.forecast import forecast, model_version
from api.services.index import index_version

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/{destination_id}", response_model=Envelope[RiskData])
def get_risk(
    destination_id: int,
    # Out of range is a 422 before this function runs.
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    destination = db.get(Destination, destination_id)
    if destination is None:
        raise HTTPException(
            status_code=404, detail=f"No destination with id {destination_id}"
        )

    # Raises ForecastUnavailable if the model is untrained or the region has
    # too little history; the app turns that into a 503, never a 500.
    result = forecast(db, destination.region, month)

    data = RiskData(
        destination_id=destination_id,
        region=result.region,
        month=result.month,
        predicted_pressure=result.predicted_pressure,
        band=result.band,
        contributions=result.contributions,
    )

    # model_version names the artefact that actually produced this number,
    # not the placeholder in the environment, because the contract promises a
    # reader can reproduce the figure later.
    meta = Meta(model_version=model_version(), index_version=index_version())
    return envelope(data, meta)
