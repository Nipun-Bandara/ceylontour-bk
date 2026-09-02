"""POST /api/recommend.

Real data now. Destinations are read from Postgres, filtered on budget and
duration, then scored by the Sustainability Index.

The explanation string is deliberately left empty; F3 fills it in.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope, meta_fields
from api.models import Destination, DestinationFactor
from api.schemas.common import FactorScores
from api.schemas.recommend import (
    ExclusionSummary,
    RecommendData,
    RecommendEnvelope,
    RecommendMeta,
    RecommendRequest,
)
from api.services.explain import contributions, sentence, top_n
from api.services.index import (
    FACTOR_ORDER,
    affordable,
    apply_preference,
    load_weights,
    score,
)

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=RecommendEnvelope)
def recommend(
    request: RecommendRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    # Raises InvalidInput for an unknown preference, which the app turns into
    # a 422 rather than a 500.
    weights = apply_preference(
        load_weights()["weights"], request.sustainability_weight
    )

    rows = db.execute(
        select(Destination, DestinationFactor).outerjoin(
            DestinationFactor,
            DestinationFactor.destination_id == Destination.id,
        )
    ).all()

    over_budget = 0
    over_duration = 0
    missing_factors = 0
    excluded_total = 0
    results = []

    for destination, factors in rows:
        # Budget and duration are filters applied before scoring. A
        # destination that does not fit is excluded, not given a low score
        # (features.md F2).
        too_expensive = not affordable(destination.cost_band, request.budget_lkr)
        too_long = destination.typical_days > request.duration_days
        no_factors = factors is None

        if too_expensive:
            over_budget += 1
        if too_long:
            over_duration += 1
        if no_factors:
            missing_factors += 1

        if too_expensive or too_long or no_factors:
            excluded_total += 1
            continue

        values = {
            factor: getattr(factors, factor) for factor in FACTOR_ORDER
        }
        total, _ = score(values, weights)

        results.append(
            {
                "destination_id": destination.id,
                "name": destination.name,
                "sustainability_score": round(total),
                "factors": FactorScores(
                    **{factor: round(values[factor]) for factor in FACTOR_ORDER}
                ),
                # Always "exact" here: computed from the weights, not estimated.
                "contributions": top_n(contributions(values, weights)),
                # Filled in below, once the ranking is known.
                "explanation": "",
                "confidence": factors.confidence,
                # Sort key only, dropped by the response model.
                "_score": total,
            }
        )

    # Highest score first, name as a tie-break so the order is stable.
    results.sort(key=lambda row: (-row["_score"], row["name"]))

    # The sentence depends on position, so it can only be written after the
    # sort. Everything below the top is explained against the result directly
    # above it.
    for position, row in enumerate(results):
        higher = results[position - 1]["name"] if position > 0 else None
        row["explanation"] = sentence(row["contributions"], higher)
        del row["_score"]

    return envelope(
        RecommendData(results=results),
        RecommendMeta(
            **meta_fields(),
            excluded=ExclusionSummary(
                total=excluded_total,
                over_budget=over_budget,
                over_duration=over_duration,
                missing_factors=missing_factors,
            ),
        ),
    )
