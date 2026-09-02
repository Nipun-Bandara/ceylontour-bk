"""Tests for the Sustainability Index itself.

Pure arithmetic, no database and no HTTP. These are the ones that prove the
index behaves the way the proposal claims it does.

Rounding contributions to whole percentages belongs to the explanation layer,
so those tests live in test_explain_service.py.
"""

import pytest

from api.services.index import (
    FACTOR_ORDER,
    InvalidInput,
    apply_preference,
    load_weights,
    score,
)

BASE_FACTORS = {
    "environmental": 80.0,
    "community": 70.0,
    "crowd": 60.0,
    "infrastructure": 50.0,
    "suitability": 40.0,
}


def base_weights() -> dict[str, float]:
    return dict(load_weights()["weights"])


@pytest.mark.parametrize("preference", ["low", "medium", "high"])
def test_weights_sum_to_one_after_preference(preference: str) -> None:
    """features.md F2: weights sum to 1.0 after any user adjustment."""
    weights = apply_preference(base_weights(), preference)
    assert weights.keys() == set(FACTOR_ORDER)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)


def test_high_preference_raises_the_sustainability_group() -> None:
    config = load_weights()
    low = apply_preference(base_weights(), "low")
    high = apply_preference(base_weights(), "high")

    def group_total(weights: dict[str, float]) -> float:
        return sum(weights[factor] for factor in config["sustainability_group"])

    assert group_total(high) > group_total(low)
    # The shift is 0.10 each way from a base of 0.75.
    assert group_total(high) == pytest.approx(0.85, abs=1e-9)
    assert group_total(low) == pytest.approx(0.65, abs=1e-9)


def test_medium_preference_leaves_the_base_weights_alone() -> None:
    weights = apply_preference(base_weights(), "medium")
    for factor, weight in base_weights().items():
        assert weights[factor] == pytest.approx(weight, abs=1e-9)


def test_unknown_preference_is_invalid_input() -> None:
    with pytest.raises(InvalidInput, match="sustainability_weight"):
        apply_preference(base_weights(), "very high")


def test_contributions_sum_to_the_total_score() -> None:
    """Percentages sum to 100, and converted back they sum to the score."""
    weights = apply_preference(base_weights(), "medium")
    total, percentages = score(BASE_FACTORS, weights)

    assert sum(percentages.values()) == pytest.approx(100.0, abs=0.01)

    rebuilt = sum(percent / 100.0 * total for percent in percentages.values())
    assert rebuilt == pytest.approx(total, abs=0.01)


def test_score_is_between_0_and_100() -> None:
    weights = apply_preference(base_weights(), "medium")

    worst, _ = score(dict.fromkeys(FACTOR_ORDER, 0.0), weights)
    best, _ = score(dict.fromkeys(FACTOR_ORDER, 100.0), weights)

    assert worst == pytest.approx(0.0, abs=1e-9)
    assert best == pytest.approx(100.0, abs=1e-9)


@pytest.mark.parametrize("preference", ["low", "medium", "high"])
def test_raising_environmental_never_lowers_the_score(preference: str) -> None:
    """Direction has to be sensible or the explanation is nonsense."""
    weights = apply_preference(base_weights(), preference)

    previous = -1.0
    for value in range(0, 101, 5):
        factors = {**BASE_FACTORS, "environmental": float(value)}
        total, _ = score(factors, weights)
        assert total >= previous
        previous = total


def test_all_zero_factors_do_not_divide_by_zero() -> None:
    weights = apply_preference(base_weights(), "medium")
    total, percentages = score(dict.fromkeys(FACTOR_ORDER, 0.0), weights)

    assert total == 0.0
    assert sum(percentages.values()) == pytest.approx(100.0, abs=0.01)


def test_weights_are_cached() -> None:
    """load_weights reads the file once, so scoring does not hit the disk."""
    assert load_weights() is load_weights()
