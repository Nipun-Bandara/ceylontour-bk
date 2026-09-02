"""GET /api/destinations and GET /api/destinations/{id}.

Real data. The list feeds the map's markers, the detail feeds the panel that
opens when one is clicked (features.md F7).

Bands are imported from the forecast service, not recomputed here, so a marker
can never disagree with the risk screen about what colour a destination is.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope
from api.models import Destination, DestinationFactor
from api.schemas.common import Envelope, FactorScores
from api.schemas.destinations import DestinationDetail, DestinationListData
from api.services.forecast import forecast
from api.services.index import FACTOR_ORDER, apply_preference, load_weights, score

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


def _neutral_weights() -> dict[str, float]:
    """Scoring weights with no user preference applied.

    These endpoints answer "what is this place like", not "what is it like for
    me", so there is no sustainability_weight to honour.
    """
    return apply_preference(load_weights()["weights"], "medium")


def _require_factors(
    destination: Destination, factors: DestinationFactor | None
) -> DestinationFactor:
    if factors is None:
        # The destination exists; what is missing is our data about it. Not
        # the caller's mistake, so not a 4xx.
        raise HTTPException(
            status_code=503,
            detail=(
                f"Destination {destination.id} has no factor values recorded, "
                "so it cannot be scored."
            ),
        )
    return factors


def _summary_fields(
    destination: Destination,
    factors: DestinationFactor,
    weights: dict[str, float],
    band: str,
) -> dict[str, Any]:
    values = {factor: float(getattr(factors, factor)) for factor in FACTOR_ORDER}
    total, _ = score(values, weights)
    return {
        "id": destination.id,
        "name": destination.name,
        "lat": destination.lat,
        "lon": destination.lon,
        "district": destination.district,
        "region": destination.region,
        "sustainability_score": round(total),
        "band": band,
    }


@router.get("", response_model=Envelope[DestinationListData])
def list_destinations(db: Session = Depends(get_db)) -> dict[str, Any]:
    weights = _neutral_weights()
    month = date.today().month

    rows = db.execute(
        select(Destination, DestinationFactor)
        .outerjoin(
            DestinationFactor,
            DestinationFactor.destination_id == Destination.id,
        )
        .order_by(Destination.id)
    ).all()

    destinations = []
    for destination, factors in rows:
        # forecast caches per (region, month), so a dozen destinations across
        # three regions costs three predictions, not a dozen.
        band = forecast(db, destination.region, month).band
        destinations.append(
            _summary_fields(
                destination, _require_factors(destination, factors), weights, band
            )
        )

    return envelope(DestinationListData(destinations=destinations))


@router.get("/{destination_id}", response_model=Envelope[DestinationDetail])
def get_destination(
    destination_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    destination = db.get(Destination, destination_id)
    if destination is None:
        raise HTTPException(
            status_code=404, detail=f"No destination with id {destination_id}"
        )

    factors = _require_factors(
        destination, db.get(DestinationFactor, destination_id)
    )
    band = forecast(db, destination.region, date.today().month).band

    data = DestinationDetail(
        **_summary_fields(destination, factors, _neutral_weights(), band),
        factors=FactorScores(
            **{
                factor: round(float(getattr(factors, factor)))
                for factor in FACTOR_ORDER
            }
        ),
        confidence=factors.confidence,
        activities=list(destination.activities or []),
        cost_band=destination.cost_band,
        typical_days=destination.typical_days,
        source_ref=factors.source_ref,
    )
    return envelope(data)
