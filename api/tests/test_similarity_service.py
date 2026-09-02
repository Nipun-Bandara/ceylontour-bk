"""Tests for the similarity vectors themselves.

Pure arithmetic. No database, no model, no HTTP.
"""

from dataclasses import dataclass, field

import pytest

from api.services.similarity import (
    build_vector,
    cosine_similarity,
    cost_band_scale,
    haversine_km,
    reason,
    similarities,
    similarity_percent,
)


@dataclass
class FakeDestination:
    id: int
    landscape_type: str = "mountain"
    activities: list[str] = field(default_factory=lambda: ["hiking"])
    cost_band: str = "low"
    lat: float = 6.9
    lon: float = 80.8


def test_haversine_matches_a_known_distance() -> None:
    """Colombo to Kandy is about 95km in a straight line."""
    distance = haversine_km(6.9271, 79.8612, 7.2906, 80.6337)
    assert 90 < distance < 100


def test_haversine_is_zero_for_the_same_point() -> None:
    assert haversine_km(6.9, 80.8, 6.9, 80.8) == pytest.approx(0.0)


def test_haversine_is_symmetric() -> None:
    there = haversine_km(6.9, 80.8, 7.3, 80.6)
    back = haversine_km(7.3, 80.6, 6.9, 80.8)
    assert there == pytest.approx(back)


def test_identical_destinations_score_one() -> None:
    source = FakeDestination(id=1)
    twin = FakeDestination(id=2)

    scores = similarities(source, [twin])
    assert scores[2] == pytest.approx(1.0)


def test_nothing_in_common_scores_low() -> None:
    source = FakeDestination(
        id=1, landscape_type="mountain", activities=["hiking"]
    )
    other = FakeDestination(
        id=2,
        landscape_type="beach",
        activities=["surfing"],
        lat=6.0,
        lon=81.2,
    )

    scores = similarities(source, [other])
    assert scores[2] < 0.5


def test_shared_activities_beat_no_shared_activities() -> None:
    source = FakeDestination(id=1, activities=["hiking", "waterfalls"])
    close = FakeDestination(id=2, activities=["hiking", "waterfalls"])
    far = FakeDestination(id=3, activities=["surfing"], landscape_type="beach")

    scores = similarities(source, [close, far])
    assert scores[2] > scores[3]


def test_closer_destination_scores_higher_when_all_else_is_equal() -> None:
    source = FakeDestination(id=1, lat=6.9, lon=80.8)
    near = FakeDestination(id=2, lat=6.95, lon=80.85)
    far = FakeDestination(id=3, lat=9.5, lon=80.0)

    scores = similarities(source, [near, far])
    assert scores[2] > scores[3]


def test_cost_band_scale_is_ordered_and_non_zero() -> None:
    """A zero component would make "both are cheap" count as no resemblance."""
    scale = cost_band_scale()
    assert scale["low"] < scale["medium"] < scale["high"]
    assert scale["low"] > 0
    assert scale["high"] == pytest.approx(1.0)


def test_cosine_of_a_zero_vector_is_zero_not_an_error() -> None:
    import numpy as np

    assert cosine_similarity(np.zeros(3), np.ones(3)) == 0.0
    assert cosine_similarity(np.ones(3), np.zeros(3)) == 0.0


def test_vector_layout_is_stable_across_calls() -> None:
    source = FakeDestination(id=1)
    others = [
        FakeDestination(id=2, landscape_type="forest", activities=["birding"]),
        FakeDestination(id=3, landscape_type="beach", activities=["surfing"]),
    ]
    landscapes = ["beach", "forest", "mountain"]
    activities = ["birding", "hiking", "surfing"]

    first = build_vector(source, source, landscapes, activities, 100.0)
    second = build_vector(source, source, landscapes, activities, 100.0)
    assert (first == second).all()

    # Same answer whichever order the candidates arrive in.
    assert similarities(source, others) == similarities(source, others[::-1])


def test_all_candidates_at_the_same_point_do_not_divide_by_zero() -> None:
    source = FakeDestination(id=1, lat=6.9, lon=80.8)
    twin = FakeDestination(id=2, lat=6.9, lon=80.8)

    scores = similarities(source, [twin])
    assert scores[2] == pytest.approx(1.0)


def test_no_candidates_gives_no_scores() -> None:
    assert similarities(FakeDestination(id=1), []) == {}


def test_similarity_percent_is_clamped() -> None:
    assert similarity_percent(0.871) == 87
    assert similarity_percent(1.5) == 100
    assert similarity_percent(-0.2) == 0


def test_reason_uses_the_template() -> None:
    assert reason("mountain", "low") == (
        "Similar mountain setting with low visitor pressure."
    )
