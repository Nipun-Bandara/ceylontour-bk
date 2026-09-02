"""The Sustainability Index.

A transparent weighted sum. There is no learned model here and there is not
meant to be one: the point of the index is that every contribution can be
shown exactly, which is what lets the UI label these as "exact" while SHAP
values are labelled "estimated".

Weights come from config/weights.yaml and are never hardcoded (CLAUDE.md hard
rule 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).parents[2] / "config"
WEIGHTS_PATH = CONFIG_DIR / "weights.yaml"
COST_BANDS_PATH = CONFIG_DIR / "cost_bands.yaml"

# The five factors, in the order the API returns them. These are names, not
# weights, so listing them here does not break hard rule 3. load_weights
# checks the config still matches, so the two cannot drift apart quietly.
FACTOR_ORDER = (
    "environmental",
    "community",
    "crowd",
    "infrastructure",
    "suitability",
)

# Anything the caller got wrong, as opposed to anything we got wrong. The API
# turns this into a 422, never a 500 (CLAUDE.md hard rule 2).
class InvalidInput(ValueError):
    pass


@lru_cache(maxsize=1)
def load_weights() -> dict[str, Any]:
    """Read config/weights.yaml once and cache it.

    lru_cache means the file is parsed on the first request and not again, so
    scoring 20 destinations does not touch the disk 20 times. Restart the app
    after editing the file.
    """
    with WEIGHTS_PATH.open() as handle:
        config = yaml.safe_load(handle)

    weights = config["weights"]

    if set(weights) != set(FACTOR_ORDER):
        raise ValueError(
            f"{WEIGHTS_PATH.name}: weights must name exactly "
            f"{', '.join(FACTOR_ORDER)}"
        )

    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"{WEIGHTS_PATH.name}: base weights sum to {total}, expected 1.0"
        )

    grouped = set(config["sustainability_group"]) | set(config["personal_group"])
    if grouped != set(FACTOR_ORDER):
        raise ValueError(
            f"{WEIGHTS_PATH.name}: the two groups must cover all five factors"
        )

    return config


@lru_cache(maxsize=1)
def load_cost_bands() -> dict[str, Any]:
    """Read config/cost_bands.yaml once and cache it."""
    with COST_BANDS_PATH.open() as handle:
        return yaml.safe_load(handle)


def index_version() -> str:
    return str(load_weights()["version"])


def apply_preference(
    weights: Mapping[str, float], sustainability_weight: str
) -> dict[str, float]:
    """Shift weight between the two groups, then renormalise to exactly 1.0.

    The shift moves a fixed amount from the personal-fit group to the
    sustainability group. Inside each group the split stays proportional, so
    "high" makes all three sustainability factors matter more relative to the
    other two without changing their order among themselves.
    """
    config = load_weights()
    shifts = config["shift"]

    if sustainability_weight not in shifts:
        allowed = ", ".join(sorted(shifts))
        raise InvalidInput(
            f"sustainability_weight must be one of: {allowed}"
        )

    amount = float(shifts[sustainability_weight])
    sustainability = list(config["sustainability_group"])
    personal = list(config["personal_group"])

    sustainability_total = sum(weights[factor] for factor in sustainability)
    personal_total = sum(weights[factor] for factor in personal)

    # Clamped so a large shift in config cannot drive a group negative.
    new_sustainability = min(
        max(sustainability_total + amount, 0.0),
        sustainability_total + personal_total,
    )
    new_personal = (sustainability_total + personal_total) - new_sustainability

    shifted: dict[str, float] = {}
    for group, old_total, new_total in (
        (sustainability, sustainability_total, new_sustainability),
        (personal, personal_total, new_personal),
    ):
        for factor in group:
            # Proportional split within the group. If the group somehow had no
            # weight at all, spread the new total evenly instead of dividing
            # by zero.
            share = (
                weights[factor] / old_total if old_total > 0 else 1 / len(group)
            )
            shifted[factor] = share * new_total

    # Renormalise so the result sums to exactly 1.0 despite float arithmetic.
    total = sum(shifted.values())
    return {factor: value / total for factor, value in shifted.items()}


def score(
    destination_factors: Mapping[str, float], weights: Mapping[str, float]
) -> tuple[float, dict[str, float]]:
    """Return (total score 0-100, {factor: contribution percent}).

    Each factor value is 0-100 and the weights sum to 1.0, so the weighted sum
    is also 0-100. A contribution is weight * factor value, expressed as a
    percent of that total, which is what the explanation bars show.
    """
    weighted = {
        factor: weights[factor] * float(destination_factors[factor])
        for factor in weights
    }
    total = sum(weighted.values())

    if total <= 0:
        # Every factor is zero. Splitting 100% evenly is more honest than
        # dividing by zero or claiming one factor drove the result.
        even = 100.0 / len(weighted) if weighted else 0.0
        return 0.0, {factor: even for factor in weighted}

    percentages = {
        factor: 100.0 * value / total for factor, value in weighted.items()
    }
    return total, percentages


def affordable(cost_band: str, budget_lkr: int) -> bool:
    """Whether budget_lkr covers a destination in this cost band."""
    minimums = load_cost_bands()["minimum_budget_lkr"]
    # An unknown band is treated as unaffordable rather than silently allowed,
    # so a typo in the dataset shows up as an exclusion instead of a bad
    # recommendation.
    if cost_band not in minimums:
        return False
    return budget_lkr >= minimums[cost_band]
