"""POST /api/simulate.

Real scoring now. The three sliders are mapped onto three of the five factor
values and the *same* Sustainability Index is run again. There is no separate
simulation model and there must not be one: if the simulator computed a score
any other way, the number it shows would not be the number the recommendation
was based on, and the whole point of the feature would go.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope
from api.models import Destination, DestinationFactor
from api.schemas.common import Envelope, FactorScores
from api.schemas.simulate import SimulateData, SimulateRequest
from api.services.explain import contributions, top_n
from api.services.index import FACTOR_ORDER, apply_preference, load_weights, score

router = APIRouter(prefix="/api", tags=["simulate"])

# F6: warn when a change costs more than this many points.
WARNING_THRESHOLD = 10

WARNING_TEMPLATE = (
    "This combination lowers the sustainability score by {points} points."
)


def apply_sliders(
    stored: dict[str, float],
    expected_tourists: int,
    waste_management_level: int,
    infrastructure_level: int,
) -> dict[str, float]:
    """Map the three sliders onto three factor values.

    This is input translation, not scoring. The scoring is untouched.

    - expected_tourists drives **crowd**, inverted. The crowd factor scores
      *low pressure*, so a busy destination has a low crowd value. More
      expected visitors therefore has to mean a smaller number.
    - waste_management_level drives **environmental**, directly.
    - infrastructure_level drives **infrastructure**, directly.

    community and suitability are left at their stored values. Nothing on the
    panel claims to change them, so inventing movement would be dishonest.

    Inverting crowd this way is also what makes a reset exact: sending
    100 - stored_crowd puts the crowd value back exactly where it started.
    """
    return {
        **stored,
        "crowd": float(100 - expected_tourists),
        "environmental": float(waste_management_level),
        "infrastructure": float(infrastructure_level),
    }


@router.post("/simulate", response_model=Envelope[SimulateData])
def simulate(
    request: SimulateRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    destination = db.get(Destination, request.destination_id)
    if destination is None:
        raise HTTPException(
            status_code=404,
            detail=f"No destination with id {request.destination_id}",
        )

    factors = db.get(DestinationFactor, request.destination_id)
    if factors is None:
        # The destination exists but has no factor values, so there is no
        # baseline to simulate against. Not the caller's mistake.
        raise HTTPException(
            status_code=503,
            detail=(
                f"Destination {request.destination_id} has no factor values "
                "recorded, so it cannot be simulated."
            ),
        )

    # The neutral preference, so the simulator compares like with like. The
    # request carries no sustainability_weight; see the branch notes.
    weights = apply_preference(load_weights()["weights"], "medium")

    stored = {factor: float(getattr(factors, factor)) for factor in FACTOR_ORDER}
    adjusted = apply_sliders(
        stored,
        request.expected_tourists,
        request.waste_management_level,
        request.infrastructure_level,
    )

    baseline_total, _ = score(stored, weights)
    adjusted_total, _ = score(adjusted, weights)

    baseline_score = round(baseline_total)
    sustainability_score = round(adjusted_total)
    delta = sustainability_score - baseline_score

    warning = None
    if delta < -WARNING_THRESHOLD:
        warning = WARNING_TEMPLATE.format(points=abs(delta))

    data = SimulateData(
        destination_id=request.destination_id,
        baseline_score=baseline_score,
        sustainability_score=sustainability_score,
        delta=delta,
        factors=FactorScores(
            **{factor: round(adjusted[factor]) for factor in FACTOR_ORDER}
        ),
        # Same explanation layer as the recommendation, so the bars mean the
        # same thing on both screens.
        contributions=top_n(contributions(adjusted, weights)),
        warning=warning,
    )
    return envelope(data)
