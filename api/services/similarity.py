"""How alike two destinations are.

Used by GET /api/alternatives/{id} to answer "this one is crowded, where else
could I go that feels the same?". Cosine similarity over an attribute vector
built from what the destination is (landscape, activities, cost band) and how
far it is from the one the user picked.

features.md F5 lists climate as a fourth attribute. There is no climate column
in the schema yet, so cost band stands in for now. That is a gap, not a
decision, and it is written down in the branch notes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from api.services.index import load_cost_bands

EARTH_RADIUS_KM = 6371.0

# Fixed template. No free text anywhere in the API's user-facing strings, for
# the same reason as the F3 sentences: every word has to be accountable.
#
# KNOWN PROBLEM. The landscape named is the *alternative's* own, and the word
# "Similar" assumes it matches the destination the user picked. When it does
# not, a forest offered against a mountain reads "Similar forest setting",
# which claims a resemblance that is not there.
#
# The fix is a second template for when the landscapes differ, something like
# "A {landscape_type} alternative with {pressure_band} visitor pressure". That
# changes user-facing wording, so it wants agreeing rather than slipping in.
REASON_TEMPLATE = (
    "Similar {landscape_type} setting with {pressure_band} visitor pressure."
)

NO_MATCH_MESSAGE = (
    "No similar destination with lower visitor pressure was found. Showing "
    "nothing is better than showing a poor match."
)


class HasAttributes(Protocol):
    """What similarity needs from a destination. The SQLAlchemy model fits."""

    id: int
    landscape_type: str
    activities: list[str]
    cost_band: str
    lat: float
    lon: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def cost_band_scale() -> dict[str, float]:
    """Each cost band as a number between 0 and 1.

    Derived from the budgets already in config/cost_bands.yaml rather than
    invented here, and deliberately not starting at zero: a zero component
    contributes nothing to a cosine, so "both are cheap" would count as no
    resemblance at all.
    """
    minimums = load_cost_bands()["minimum_budget_lkr"]
    largest = max(minimums.values())
    return {band: value / largest for band, value in minimums.items()}


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Cosine of the angle between two vectors, 0 if either has no length."""
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _vocabularies(
    destinations: Sequence[HasAttributes],
) -> tuple[list[str], list[str]]:
    """Sorted lists of every landscape type and activity in play.

    Sorted so the vector layout is the same on every request; the same two
    destinations must never score differently because of dictionary order.
    """
    landscapes = sorted({str(item.landscape_type) for item in destinations})
    activities = sorted(
        {activity for item in destinations for activity in (item.activities or [])}
    )
    return landscapes, activities


def build_vector(
    destination: HasAttributes,
    selected: HasAttributes,
    landscapes: Sequence[str],
    activities: Sequence[str],
    max_distance_km: float,
) -> np.ndarray:
    """One destination as a vector, relative to the one the user picked.

    Four blocks joined together: landscape one-hot, activities multi-hot, cost
    band as a single scaled number, and closeness to the selected destination.
    Distance is inverted so that near means a large value, because cosine
    rewards agreement on large components.
    """
    landscape_block = [
        1.0 if destination.landscape_type == name else 0.0 for name in landscapes
    ]

    owned = set(destination.activities or [])
    activity_block = [1.0 if name in owned else 0.0 for name in activities]

    scale = cost_band_scale()
    # An unknown band scores 0 rather than guessing where it sits.
    cost_block = [float(scale.get(destination.cost_band, 0.0))]

    distance = haversine_km(
        selected.lat, selected.lon, destination.lat, destination.lon
    )
    # If every candidate sits on the same spot there is nothing to scale by,
    # so distance simply stops being a distinguishing feature.
    closeness = 1.0 if max_distance_km == 0 else 1.0 - (distance / max_distance_km)
    distance_block = [closeness]

    return np.array(
        [*landscape_block, *activity_block, *cost_block, *distance_block],
        dtype=float,
    )


def similarities(
    selected: HasAttributes, candidates: Sequence[HasAttributes]
) -> dict[int, float]:
    """Cosine similarity of each candidate to the selected destination.

    Vectors are built per request because the distance block is measured from
    whichever destination the user picked.
    """
    if not candidates:
        return {}

    everything = [selected, *candidates]
    landscapes, activities = _vocabularies(everything)

    max_distance = max(
        haversine_km(selected.lat, selected.lon, item.lat, item.lon)
        for item in candidates
    )

    selected_vector = build_vector(
        selected, selected, landscapes, activities, max_distance
    )
    return {
        int(candidate.id): cosine_similarity(
            selected_vector,
            build_vector(
                candidate, selected, landscapes, activities, max_distance
            ),
        )
        for candidate in candidates
    }


def similarity_percent(similarity: float) -> int:
    """Cosine as a whole percentage, clamped to the schema's 0-100."""
    return int(round(min(max(similarity, 0.0), 1.0) * 100))


def reason(landscape_type: str, pressure_band: str) -> str:
    """The one-sentence explanation shown beside an alternative."""
    return REASON_TEMPLATE.format(
        landscape_type=landscape_type, pressure_band=pressure_band
    )
