"""Feature engineering for the visitor pressure model.

The model predicts a region's occupancy rate for a month (features.md F4).
Everything here is built only from information that would be known *before*
that month starts: past occupancy, past arrivals, and the calendar. The
current month's arrivals and guest nights are never used, because in a real
forecast they have not happened yet. Using them would make the evaluation
look good and the model useless.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGET = "occupancy_rate"
REGION = "region"

# Sri Lanka's two peak windows: the December-March northern winter season and
# the shorter July-August season.
PEAK_SEASON_MONTHS = frozenset({12, 1, 2, 3, 7, 8})

# features.md F4 sets the minimum for a series worth training on. Below this
# the scripts still run, but they say loudly that the result is thin.
MIN_MONTHS = 36

NUMERIC_FEATURES = [
    "month",
    "month_sin",
    "month_cos",
    "is_peak_season",
    "occupancy_lag_1",
    "occupancy_lag_2",
    "occupancy_lag_12",
    "occupancy_rolling_3",
    "arrivals_trend",
]

# region is categorical; LightGBM handles it natively as a pandas category.
FEATURE_COLUMNS = [*NUMERIC_FEATURES, REGION]

REQUIRED_COLUMNS = [REGION, "year", "month", TARGET, "arrivals", "guest_nights"]


class InsufficientData(RuntimeError):
    """Not enough history to do what was asked."""


def period_index(year: pd.Series, month: pd.Series) -> pd.Series:
    """A single increasing integer per calendar month.

    Used for ordering and for spotting gaps, so "lag 1" really means last
    month rather than "the previous row we happen to have".
    """
    return year.astype(int) * 12 + (month.astype(int) - 1)


def months_covered(history: pd.DataFrame) -> int:
    """How many distinct calendar months the series covers."""
    if history.empty:
        return 0
    periods = period_index(history["year"], history["month"])
    return int(periods.max() - periods.min()) + 1


def _region_frame(group: pd.DataFrame) -> pd.DataFrame:
    """Lags for one region, on a gap-free monthly index.

    The group is reindexed over every month between its first and last
    observation. Without this a missing month would silently shift the lags,
    so "last month" could actually mean "three months ago".
    """
    group = group.sort_values("period")
    full = pd.RangeIndex(int(group["period"].min()), int(group["period"].max()) + 1)
    group = group.set_index("period").reindex(full)
    group.index.name = "period"

    occupancy = group[TARGET]
    arrivals = group["arrivals"]

    group["occupancy_lag_1"] = occupancy.shift(1)
    group["occupancy_lag_2"] = occupancy.shift(2)
    group["occupancy_lag_12"] = occupancy.shift(12)

    # shift(1) before rolling, so the window is the three months *before* the
    # one being predicted and never includes the answer.
    group["occupancy_rolling_3"] = occupancy.shift(1).rolling(3).mean()

    # Direction of travel in arrivals, from the two most recent completed
    # months. A zero denominator gives NaN, which drops the row later rather
    # than inventing a number.
    previous = arrivals.shift(1)
    before = arrivals.shift(2)
    group["arrivals_trend"] = (previous - before) / before.replace(0, np.nan)

    return group.reset_index()


def build_features(history: pd.DataFrame) -> pd.DataFrame:
    """Turn raw region_pressure_history rows into a model frame.

    Rows whose lags cannot be computed yet keep their NaNs here. model_frame()
    is what drops them, so the caller can see how many were lost.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in history.columns]
    if missing:
        raise InsufficientData(
            f"history is missing column(s): {', '.join(missing)}"
        )

    history = history.copy()
    history["period"] = period_index(history["year"], history["month"])

    # One region at a time, so a lag never reaches across regions. A plain
    # loop rather than groupby.apply, because the reindex inside changes the
    # shape and the loop is easier to follow.
    built = []
    for region, group in history.groupby(REGION, sort=True):
        region_frame = _region_frame(group)
        # The reindex leaves region blank on filled-in months; the group key
        # is the real answer.
        region_frame[REGION] = str(region)
        built.append(region_frame)

    frame = pd.concat(built, ignore_index=True)

    frame["year"] = (frame["period"] // 12).astype(int)
    frame["month"] = (frame["period"] % 12 + 1).astype(int)

    # Calendar features. These are known in advance for any future month.
    frame["month_sin"] = np.sin(2 * np.pi * frame["month"] / 12)
    frame["month_cos"] = np.cos(2 * np.pi * frame["month"] / 12)
    frame["is_peak_season"] = (
        frame["month"].isin(PEAK_SEASON_MONTHS).astype(int)
    )

    return frame.sort_values([REGION, "period"]).reset_index(drop=True)


def model_frame(features: pd.DataFrame) -> pd.DataFrame:
    """Only the rows that can actually be trained or scored on.

    Drops any row with a missing target (a month the reindex invented) or a
    missing feature (the first twelve months of each region, which have no
    lag-12 yet). Nothing with a NaN reaches the model.
    """
    complete = features.dropna(subset=[TARGET, *NUMERIC_FEATURES])
    return complete.reset_index(drop=True)


def as_categorical(
    frame: pd.DataFrame, categories: list[str] | None = None
) -> pd.DataFrame:
    """Give region a fixed category order.

    The order is saved alongside the model, because LightGBM stores category
    codes rather than names. Loading a model with a different order would map
    every region to the wrong one, silently.
    """
    frame = frame.copy()
    if categories is None:
        categories = sorted(frame[REGION].astype(str).unique())
    frame[REGION] = pd.Categorical(
        frame[REGION].astype(str), categories=categories
    )
    return frame


def most_recent_full_year(frame: pd.DataFrame) -> int | None:
    """The latest calendar year with all twelve months present."""
    if frame.empty:
        return None
    counts = frame.groupby("year")["month"].nunique()
    complete = counts[counts == 12]
    return int(complete.index.max()) if len(complete) else None


def time_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Split on time, never at random.

    The test set is the most recent full calendar year. Training is everything
    strictly before it. Anything *after* the test year, such as a part-finished
    current year, is dropped from both sides so the split stays a clean line in
    time.
    """
    year = most_recent_full_year(frame)
    if year is None:
        raise InsufficientData(
            "no complete calendar year in the data, so there is nothing to "
            "hold out as a test set"
        )

    train = frame[frame["year"] < year].reset_index(drop=True)
    test = frame[frame["year"] == year].reset_index(drop=True)

    if train.empty:
        raise InsufficientData(
            f"the only complete year is {year}, leaving nothing to train on"
        )

    # The guarantee this whole function exists for. A raise rather than an
    # assert, because asserts vanish under python -O and this one must not.
    if train["period"].max() >= test["period"].min():
        raise InsufficientData(
            "training data overlaps the held-out year, which would leak the "
            "answers into the model"
        )

    return train, test, year
