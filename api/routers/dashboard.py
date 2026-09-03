"""GET /api/dashboard/summary.

The authority view, behind a login. Real numbers, and a recommended action
built from those numbers rather than written in advance.
"""

from collections import Counter
from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope
from api.models import Destination, RegionPressureHistory, User
from api.schemas.common import Envelope
from api.schemas.dashboard import DashboardSummaryData
from api.services.explain import global_shap_importance
from api.services.forecast import forecast, load_model
from api.services.security import require_authority
from ml.features import as_categorical, build_features, model_frame

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# F8 shows the worst offenders, not the whole table.
TOP_PRESSURE_COUNT = 5

# Fixed templates. The numbers and the region name come from the data; the
# words never change. "Recommended action text is generated from the data, not
# hardcoded" is an acceptance criterion, and a template with a slot in it is
# how that is done without free-text generation.
ACTION_TEMPLATES = {
    "none": "No destinations are being monitored yet.",
    "high_one": (
        "1 destination is at high pressure this month. Consider promoting "
        "lower-pressure alternatives in {region}."
    ),
    "high_many": (
        "{count} destinations are at high pressure this month. Consider "
        "promoting lower-pressure alternatives in {region}."
    ),
    "medium_one": (
        "No destination is at high pressure this month. 1 is at medium "
        "pressure and worth watching in {region}."
    ),
    "medium_many": (
        "No destination is at high pressure this month. {count} are at medium "
        "pressure and worth watching, {region} most of all."
    ),
    "all_low": (
        "All {count} monitored destinations are at low pressure this month. "
        "No action needed."
    ),
}


def recommended_action(
    band_counts: Counter[str], regions_by_band: dict[str, Counter[str]]
) -> str:
    """Pick a template and fill it from the counts."""
    total = sum(band_counts.values())
    if total == 0:
        return ACTION_TEMPLATES["none"]

    for band, singular, plural in (
        ("high", "high_one", "high_many"),
        ("medium", "medium_one", "medium_many"),
    ):
        count = band_counts.get(band, 0)
        if count:
            # The region carrying the most of them. Alphabetical on a tie, so
            # the sentence is the same every time the page is refreshed.
            region = min(
                regions_by_band[band],
                key=lambda name: (-regions_by_band[band][name], name),
            )
            key = singular if count == 1 else plural
            return ACTION_TEMPLATES[key].format(count=count, region=region)

    return ACTION_TEMPLATES["all_low"].format(count=total)


def _global_importance(db: Session) -> list[dict[str, Any]]:
    """Mean absolute SHAP across the history the model was built from."""
    booster, metadata = load_model()

    rows = db.execute(select(RegionPressureHistory)).scalars().all()
    history = pd.DataFrame(
        [
            {
                "region": row.region,
                "year": row.year,
                "month": row.month,
                "occupancy_rate": row.occupancy_rate,
                "arrivals": row.arrivals,
                "guest_nights": row.guest_nights,
            }
            for row in rows
        ]
    )
    if history.empty:
        return []

    frame = model_frame(build_features(history))
    if frame.empty:
        return []

    frame = as_categorical(frame, metadata["region_categories"])
    return global_shap_importance(
        booster, frame[metadata["features"]], metadata["features"]
    )


@router.get("/summary", response_model=Envelope[DashboardSummaryData])
def get_summary(
    db: Session = Depends(get_db),
    # Authenticated *and* an authority. A tourist token gets 403 here.
    _: User = Depends(require_authority),
) -> dict[str, Any]:
    month = date.today().month
    destinations = (
        db.execute(select(Destination).order_by(Destination.id)).scalars().all()
    )

    band_counts: Counter[str] = Counter()
    regions_by_band: dict[str, Counter[str]] = {
        "low": Counter(),
        "medium": Counter(),
        "high": Counter(),
    }
    scored = []

    for destination in destinations:
        result = forecast(db, destination.region, month)
        band_counts[result.band] += 1
        regions_by_band[result.band][destination.region] += 1
        scored.append(
            {
                "destination_id": destination.id,
                "name": destination.name,
                "region": destination.region,
                "predicted_pressure": result.predicted_pressure,
                "band": result.band,
            }
        )

    # Busiest first, name as a tie-break so the list does not reshuffle
    # between refreshes.
    scored.sort(key=lambda row: (-row["predicted_pressure"], row["name"]))

    data = DashboardSummaryData(
        # Every destination in the table is monitored, so this and the band
        # counts are two views of the same number.
        destinations_monitored=len(destinations),
        band_counts={
            "low": band_counts.get("low", 0),
            "medium": band_counts.get("medium", 0),
            "high": band_counts.get("high", 0),
        },
        highest_pressure=scored[:TOP_PRESSURE_COUNT],
        recommended_action=recommended_action(band_counts, regions_by_band),
        global_feature_importance=_global_importance(db),
    )
    return envelope(data)
