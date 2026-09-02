"""The explanation layer for the Sustainability Index.

Every recommendation has to answer "why was this recommended?" (features.md
F3). Two things do that: contribution bars, and one plain-language sentence
underneath them.

The sentences come from fixed templates with the factor names slotted in.
Nothing here generates free text. A template cannot say something the numbers
do not support, and two students can explain exactly where every word came
from.

Contributions produced here are always type "exact": they are computed
directly from the weights, unlike the SHAP values on the risk endpoint, which
are estimates. The UI has to render the two differently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from api.services.index import score

# Plain-language labels. A tourist reads these, not "environmental: 32%".
FACTOR_LABELS = {
    "environmental": "strong environmental conditions",
    "crowd": "low visitor pressure",
    "community": "high community benefit",
    "suitability": "good fit for your trip",
    "infrastructure": "solid infrastructure",
}

# The templates from features.md F3. These are the only sentences the API can
# produce.
TOP_TEMPLATE = "Recommended mainly because of {factor_1} and {factor_2}."

# KNOWN PROBLEM. The deciding factor here is the destination's *weakest*
# contributor, but every label in FACTOR_LABELS is phrased as a strength. So a
# crowded destination reads "Ranked below Meemure mainly because of low visitor
# pressure", which states the opposite of its own data.
#
# The fix is a second label map phrased as weaknesses ("higher visitor
# pressure", "weaker infrastructure") used only by this template. That changes
# user-facing wording the contract fixes, so it needs sign-off before it goes
# in rather than being slipped in here.
RANKED_BELOW_TEMPLATE = (
    "Ranked below {higher_destination} mainly because of {deciding_factor}."
)
# Used only if a caller passes fewer than two contributions. The index always
# has five, so the API never hits this.
SINGLE_FACTOR_TEMPLATE = "Recommended mainly because of {factor_1}."

# F3: top five factors shown, no more. Longer lists stop being explanations.
MAX_CONTRIBUTIONS = 5


def label(factor: str) -> str:
    """The friendly label for a factor name."""
    return FACTOR_LABELS.get(factor, factor)


def _largest_remainder(percentages: Mapping[str, float]) -> dict[str, int]:
    """Round percentages to whole numbers that still sum to exactly 100.

    Rounding each value on its own gives bars that add up to 99 or 101, and F3
    promises they sum to 100. Instead every value is floored, then the leftover
    points go to the values with the largest fractional part. Ties break on the
    factor name so the same input always gives the same output.
    """
    if not percentages:
        return {}

    floors = {factor: int(value) for factor, value in percentages.items()}
    remainder = 100 - sum(floors.values())

    ranked = sorted(
        percentages,
        key=lambda factor: (-(percentages[factor] - floors[factor]), factor),
    )
    for factor in ranked[:remainder]:
        floors[factor] += 1

    return floors


def contributions(
    factor_scores: Mapping[str, float], weights: Mapping[str, float]
) -> list[dict[str, Any]]:
    """The explanation bars, largest first.

    Percentages are whole numbers summing to exactly 100. Equal percentages are
    ordered by factor name, so the same destination always renders the same
    way.
    """
    _, percentages = score(factor_scores, weights)
    rounded = _largest_remainder(percentages)

    ordered = sorted(rounded, key=lambda factor: (-rounded[factor], factor))
    return [
        {"factor": factor, "percent": rounded[factor], "type": "exact"}
        for factor in ordered
    ]


def top_n(
    items: Sequence[Mapping[str, Any]], n: int = MAX_CONTRIBUTIONS
) -> list[dict[str, Any]]:
    """At most n contributions. F3 caps the panel at five."""
    return [dict(item) for item in items[:n]]


def sentence(
    items: Sequence[Mapping[str, Any]], destination_name: str | None = None
) -> str:
    """One sentence explaining a result.

    destination_name is the destination ranked immediately *above* this one.
    Pass None for the top result, which gets the "Recommended mainly because
    of" template; anything else gets "Ranked below".

    The deciding factor for a lower-ranked result is its weakest contributor,
    because that is the one holding it back.
    """
    if not items:
        return ""

    if destination_name:
        # Lowest contribution, name as a tie-break for determinism.
        weakest = min(
            items, key=lambda item: (item["percent"], item["factor"])
        )
        return RANKED_BELOW_TEMPLATE.format(
            higher_destination=destination_name,
            deciding_factor=label(weakest["factor"]),
        )

    # items is already sorted highest first by contributions().
    ordered = sorted(
        items, key=lambda item: (-item["percent"], item["factor"])
    )
    if len(ordered) == 1:
        return SINGLE_FACTOR_TEMPLATE.format(factor_1=label(ordered[0]["factor"]))

    return TOP_TEMPLATE.format(
        factor_1=label(ordered[0]["factor"]),
        factor_2=label(ordered[1]["factor"]),
    )
