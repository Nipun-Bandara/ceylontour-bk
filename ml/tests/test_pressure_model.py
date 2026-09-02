"""Tests for the pressure model pipeline.

These build their own synthetic series rather than reading the database, so
they run anywhere and do not depend on how much real data has been collected
yet. They check the pipeline is correct, not that the model is accurate;
accuracy is what the model card reports, honestly, on real data.
"""

import numpy as np
import pandas as pd
import pytest

from ml.evaluate import compare, mae, rmse, seasonal_baseline
from ml.features import (
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    PEAK_SEASON_MONTHS,
    REGION,
    TARGET,
    InsufficientData,
    as_categorical,
    build_features,
    model_frame,
    months_covered,
    most_recent_full_year,
    time_split,
)
from ml.train_pressure import train_model

REGIONS = ["Central", "Sabaragamuwa", "Uva"]


def make_history(
    years: range = range(2019, 2025),
    regions: list[str] | None = None,
    drop: set[tuple[str, int, int]] | None = None,
) -> pd.DataFrame:
    """A believable monthly series: seasonal, with a per-region level."""
    regions = regions or REGIONS
    drop = drop or set()
    rows = []
    for offset, region in enumerate(regions):
        for year in years:
            for month in range(1, 13):
                if (region, year, month) in drop:
                    continue
                seasonal = 20 * np.sin(2 * np.pi * (month - 3) / 12)
                peak = 8 if month in PEAK_SEASON_MONTHS else 0
                occupancy = 50 + offset * 5 + seasonal + peak
                rows.append(
                    {
                        "region": region,
                        "year": year,
                        "month": month,
                        "occupancy_rate": round(float(occupancy), 2),
                        "arrivals": int(1000 * (1 + occupancy / 100)),
                        "guest_nights": int(2200 * (1 + occupancy / 100)),
                    }
                )
    return pd.DataFrame(rows)


def test_build_features_produces_every_expected_column() -> None:
    features = build_features(make_history())
    for column in FEATURE_COLUMNS:
        assert column in features.columns


def test_no_nan_reaches_the_model() -> None:
    """The whole point of model_frame: nothing incomplete gets trained on."""
    frame = model_frame(build_features(make_history()))

    assert not frame.empty
    assert not frame[NUMERIC_FEATURES].isna().to_numpy().any()
    assert not frame[TARGET].isna().to_numpy().any()
    assert frame[REGION].notna().all()


def test_rows_without_a_full_year_of_history_are_dropped() -> None:
    """Lag-12 does not exist for the first twelve months of a region."""
    features = build_features(make_history(years=range(2020, 2023)))
    frame = model_frame(features)

    # Three regions, three years, minus the first twelve months of each.
    assert len(frame) == 3 * (36 - 12)
    assert frame["year"].min() == 2021


def test_gaps_in_the_series_do_not_shift_the_lags() -> None:
    """A missing month must not make "last month" mean "two months ago"."""
    history = make_history(
        years=range(2020, 2023), drop={("Central", 2021, 6)}
    )
    features = build_features(history)

    central = features[features[REGION] == "Central"].set_index("period")
    # June 2021 is absent from the data but present as a gap in the index.
    june = 2021 * 12 + 5
    assert june in central.index
    assert pd.isna(central.loc[june, TARGET])

    # July's lag-1 is June, which is missing, so July cannot be trained on.
    july = central.loc[june + 1]
    assert pd.isna(july["occupancy_lag_1"])

    # Dropped for Central only. The same month in other regions is unaffected,
    # which is what proves the lag did not reach across regions.
    usable = model_frame(features)
    central_periods = set(usable[usable[REGION] == "Central"]["period"])
    uva_periods = set(usable[usable[REGION] == "Uva"]["period"])
    assert (june + 1) not in central_periods
    assert (june + 1) in uva_periods


def test_rolling_mean_excludes_the_month_being_predicted() -> None:
    frame = model_frame(build_features(make_history()))
    row = frame.iloc[0]
    period = row["period"]

    source = build_features(make_history())
    region_rows = source[source[REGION] == row[REGION]].set_index("period")
    previous_three = [
        region_rows.loc[period - offset, TARGET] for offset in (1, 2, 3)
    ]

    assert row["occupancy_rolling_3"] == pytest.approx(np.mean(previous_three))
    # If the current month leaked in, this would differ.
    assert row["occupancy_rolling_3"] != pytest.approx(row[TARGET])


def test_peak_season_flag_matches_the_documented_months() -> None:
    frame = build_features(make_history())
    peak = set(frame[frame["is_peak_season"] == 1]["month"].unique())
    assert peak == set(PEAK_SEASON_MONTHS)


def test_months_covered_counts_calendar_months() -> None:
    assert months_covered(make_history(years=range(2020, 2023))) == 36
    assert months_covered(pd.DataFrame()) == 0


def test_split_has_no_future_data_in_training() -> None:
    frame = model_frame(build_features(make_history()))
    train, test, year = time_split(frame)

    assert year == most_recent_full_year(frame)
    assert train["period"].max() < test["period"].min()
    assert train["year"].max() < year
    assert set(test["year"].unique()) == {year}
    # Every held-out month is later than every training month.
    assert max(train["period"]) < min(test["period"])


def test_split_holds_out_a_whole_year_for_every_region() -> None:
    frame = model_frame(build_features(make_history()))
    _, test, _ = time_split(frame)
    assert len(test) == 12 * len(REGIONS)


def test_split_refuses_when_there_is_no_complete_year() -> None:
    history = make_history(years=range(2020, 2021))  # one year, no lag-12
    frame = model_frame(build_features(history))
    with pytest.raises(InsufficientData):
        time_split(frame)


def test_split_refuses_when_there_is_nothing_left_to_train_on() -> None:
    """One usable year cannot be both the training set and the test set."""
    frame = model_frame(build_features(make_history(years=range(2020, 2022))))
    with pytest.raises(InsufficientData, match="nothing to train on"):
        time_split(frame)


def test_evaluate_produces_both_numbers() -> None:
    frame = as_categorical(model_frame(build_features(make_history())))
    train, test, _ = time_split(frame)
    booster = train_model(train)

    results = compare(booster, train, test, FEATURE_COLUMNS)

    for key in ("model_mae", "model_rmse", "baseline_mae", "baseline_rmse"):
        assert isinstance(results[key], float)
        assert np.isfinite(results[key])
        assert results[key] >= 0
    assert isinstance(results["beat_baseline"], bool)
    # The verdict has to agree with the numbers it is drawn from.
    assert results["beat_baseline"] == (
        results["model_mae"] < results["baseline_mae"]
    )


def test_seasonal_baseline_predicts_one_value_per_test_row() -> None:
    frame = as_categorical(model_frame(build_features(make_history())))
    train, test, _ = time_split(frame)

    predictions = seasonal_baseline(train, test)

    assert len(predictions) == len(test)
    assert np.isfinite(predictions).all()


def test_seasonal_baseline_uses_the_region_and_month_mean() -> None:
    frame = as_categorical(model_frame(build_features(make_history())))
    train, test, _ = time_split(frame)

    predictions = seasonal_baseline(train, test)
    row = test.iloc[0]
    expected = train[
        (train[REGION] == row[REGION]) & (train["month"] == row["month"])
    ][TARGET].mean()

    assert predictions[0] == pytest.approx(expected)


def test_metrics_are_the_usual_definitions() -> None:
    actual = pd.Series([10.0, 20.0, 30.0])
    predicted = np.array([12.0, 18.0, 33.0])

    assert mae(actual, predicted) == pytest.approx((2 + 2 + 3) / 3)
    assert rmse(actual, predicted) == pytest.approx(
        np.sqrt((4 + 4 + 9) / 3)
    )
    assert mae(actual, np.asarray(actual, dtype=float)) == 0.0
