"""GET /api/alternatives/{id}.

Real data. When a destination is under pressure, this offers up to three
similar ones that are under less, and says nothing at all rather than padding
the list with a poor match (features.md F5).
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope
from api.models import Destination
from api.schemas.alternatives import AlternativesData
from api.schemas.common import MAX_DURATION_DAYS, Envelope
from api.services.forecast import ForecastUnavailable, forecast
from api.services.index import affordable
from api.services.similarity import (
    NO_MATCH_MESSAGE,
    reason,
    similarities,
    similarity_percent,
)

router = APIRouter(prefix="/api/alternatives", tags=["alternatives"])

# F5: three alternatives, not a longer list padded out.
MAX_ALTERNATIVES = 3


@router.get("/{destination_id}", response_model=Envelope[AlternativesData])
def get_alternatives(
    destination_id: int = Path(gt=0),
    # Optional, but when supplied an alternative must never break them.
    budget_lkr: int | None = Query(default=None, gt=0),
    duration_days: int | None = Query(
        default=None, ge=1, le=MAX_DURATION_DAYS
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    source = db.get(Destination, destination_id)
    if source is None:
        raise HTTPException(
            status_code=404, detail=f"No destination with id {destination_id}"
        )

    # No month in the contract for this endpoint, so pressure is compared for
    # the month the question is being asked in. See the branch notes: matching
    # the month of the trip would be better.
    month = date.today().month

    # If the selected destination has no forecast there is nothing to be
    # "lower than", so this one is a real 503.
    source_forecast = forecast(db, source.region, month)

    others = (
        db.execute(select(Destination).where(Destination.id != destination_id))
        .scalars()
        .all()
    )

    # Filters first. A destination the user cannot afford or has no time for is
    # not a candidate, however similar it is (features.md F5).
    candidates = [
        destination
        for destination in others
        if (budget_lkr is None or affordable(destination.cost_band, budget_lkr))
        and (duration_days is None or destination.typical_days <= duration_days)
    ]

    lower_pressure = []
    for destination in candidates:
        try:
            candidate_forecast = forecast(db, destination.region, month)
        except ForecastUnavailable:
            # One region short of history should not sink the whole request.
            # It cannot be compared, so it is not offered.
            continue
        # Strictly lower. Equal pressure is not an improvement.
        if candidate_forecast.predicted_pressure < source_forecast.predicted_pressure:
            lower_pressure.append((destination, candidate_forecast))

    scores = similarities(source, [item for item, _ in lower_pressure])

    ranked = sorted(
        lower_pressure,
        key=lambda pair: (-scores.get(int(pair[0].id), 0.0), pair[0].name),
    )[:MAX_ALTERNATIVES]

    alternatives = [
        {
            "destination_id": destination.id,
            "name": destination.name,
            "similarity_percent": similarity_percent(
                scores.get(int(destination.id), 0.0)
            ),
            "predicted_pressure": candidate_forecast.predicted_pressure,
            "band": candidate_forecast.band,
            "reason": reason(
                destination.landscape_type, candidate_forecast.band
            ),
        }
        for destination, candidate_forecast in ranked
    ]

    data = AlternativesData(
        destination_id=destination_id,
        alternatives=alternatives,
        # Say so plainly rather than filling the slots with bad matches.
        message=None if alternatives else NO_MATCH_MESSAGE,
    )
    return envelope(data)
