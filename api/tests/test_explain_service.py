"""Tests for the explanation layer.

Pure functions, no database and no HTTP, except the one test that walks the
seeded dataset.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import DestinationFactor
from api.services.explain import (
    FACTOR_LABELS,
    MAX_CONTRIBUTIONS,
    contributions,
    sentence,
    top_n,
)
from api.services.index import FACTOR_ORDER, apply_preference, load_weights

PREFERENCES = ["low", "medium", "high"]


def weights_for(preference: str = "medium") -> dict[str, float]:
    return apply_preference(dict(load_weights()["weights"]), preference)


def factors(**overrides: float) -> dict[str, float]:
    base = {
        "environmental": 80.0,
        "community": 70.0,
        "crowd": 60.0,
        "infrastructure": 50.0,
        "suitability": 40.0,
    }
    return {**base, **overrides}


@pytest.mark.parametrize("preference", PREFERENCES)
def test_percentages_sum_to_exactly_100(preference: str) -> None:
    items = contributions(factors(), weights_for(preference))
    assert sum(item["percent"] for item in items) == 100


@pytest.mark.parametrize(
    "values",
    [
        # A spread that does not divide evenly, which is where naive rounding
        # would land on 99 or 101.
        {"environmental": 83.0, "community": 61.0, "crowd": 47.0},
        # One dominant factor.
        {"environmental": 100.0, "community": 1.0, "crowd": 1.0},
        # All equal.
        dict.fromkeys(FACTOR_ORDER, 50.0),
        # Everything tiny.
        dict.fromkeys(FACTOR_ORDER, 1.0),
    ],
)
def test_percentages_sum_to_100_for_awkward_values(values: dict) -> None:
    items = contributions(factors(**values), weights_for())
    assert sum(item["percent"] for item in items) == 100


def test_contributions_are_sorted_high_to_low() -> None:
    items = contributions(factors(), weights_for())
    percents = [item["percent"] for item in items]
    assert percents == sorted(percents, reverse=True)


def test_contributions_are_all_exact() -> None:
    items = contributions(factors(), weights_for())
    assert all(item["type"] == "exact" for item in items)
    assert {item["factor"] for item in items} == set(FACTOR_ORDER)


def test_top_n_never_returns_more_than_five() -> None:
    items = contributions(factors(), weights_for())
    assert len(top_n(items)) <= MAX_CONTRIBUTIONS
    assert len(top_n(items)) == 5

    # Even if the list somehow grew, the cap holds.
    padded = [*items, *items]
    assert len(top_n(padded)) == MAX_CONTRIBUTIONS
    assert len(top_n(items, n=2)) == 2


def test_every_label_is_plain_language() -> None:
    assert set(FACTOR_LABELS) == set(FACTOR_ORDER)


def test_top_result_uses_the_recommended_template() -> None:
    items = contributions(factors(), weights_for("medium"))
    text = sentence(items)
    assert text.startswith("Recommended mainly because of ")
    assert text.endswith(".")
    # Top two contributors, in plain language.
    assert FACTOR_LABELS[items[0]["factor"]] in text
    assert FACTOR_LABELS[items[1]["factor"]] in text


def test_lower_result_uses_the_ranked_below_template() -> None:
    items = contributions(factors(), weights_for("medium"))
    text = sentence(items, "Belihuloya")
    assert text == (
        "Ranked below Belihuloya mainly because of "
        f"{FACTOR_LABELS[items[-1]['factor']]}."
    )


def test_tied_factors_give_a_stable_repeatable_sentence() -> None:
    """Ties break alphabetically, so the same input always reads the same.

    With the base weights, environmental 40 and community 60 both contribute
    12, and everything else contributes nothing.
    """
    values = {
        "environmental": 40.0,
        "community": 60.0,
        "crowd": 0.0,
        "infrastructure": 0.0,
        "suitability": 0.0,
    }
    items = contributions(values, weights_for("medium"))

    assert items[0]["percent"] == items[1]["percent"] == 50
    # "community" sorts before "environmental".
    assert [item["factor"] for item in items[:2]] == ["community", "environmental"]

    text = sentence(items)
    assert text == (
        "Recommended mainly because of high community benefit "
        "and strong environmental conditions."
    )
    # Repeatable: same answer every time, not just the first.
    for _ in range(5):
        assert sentence(contributions(values, weights_for("medium"))) == text


def test_one_dominant_factor_still_gives_a_valid_sentence() -> None:
    values = {
        "environmental": 100.0,
        "community": 0.0,
        "crowd": 0.0,
        "infrastructure": 0.0,
        "suitability": 0.0,
    }
    items = contributions(values, weights_for("medium"))

    assert items[0]["factor"] == "environmental"
    assert items[0]["percent"] == 100

    text = sentence(items)
    assert text == (
        "Recommended mainly because of strong environmental conditions "
        "and high community benefit."
    )
    assert sum(item["percent"] for item in items) == 100


def test_no_contributions_gives_an_empty_string() -> None:
    assert sentence([]) == ""


def test_every_seeded_destination_sums_to_100(db_session: Session) -> None:
    """features.md F3: percentages sum to 100 for every destination in the
    dataset, not just the convenient ones."""
    rows = db_session.execute(select(DestinationFactor)).scalars().all()
    assert rows, "no seeded destination_factors, run python -m ml.seed"

    for preference in PREFERENCES:
        weights = weights_for(preference)
        for row in rows:
            values = {factor: getattr(row, factor) for factor in FACTOR_ORDER}
            items = contributions(values, weights)
            assert sum(item["percent"] for item in items) == 100, (
                f"destination_id {row.destination_id} at {preference} preference"
            )
            # And the sentence works for it.
            assert sentence(items).startswith("Recommended mainly because of ")
