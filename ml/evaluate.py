"""Measure the pressure model against a seasonal-average baseline.

    python ml/evaluate.py

Writes ml/artifacts/model_card.md.

The baseline is the mean occupancy for that region and month across the
training years. It is trivial, and it is exactly the thing a LightGBM model
has to beat to be worth having.

If the model loses, the card says so. A team that knows its model
underperformed reads as competent; a team caught overstating does not
(features.md F4). Nothing in here suppresses or softens the comparison.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ml.features import (  # noqa: E402
    MIN_MONTHS,
    NUMERIC_FEATURES,
    REGION,
    TARGET,
    InsufficientData,
    as_categorical,
    build_features,
    model_frame,
    months_covered,
    time_split,
)
from ml.train_pressure import (  # noqa: E402
    FEATURES_PATH,
    MODEL_PATH,
    MODEL_VERSION,
    read_history,
)

CARD_PATH = Path(__file__).parent / "artifacts" / "model_card.md"


def mae(actual: pd.Series, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(actual, dtype=float) - predicted)))


def rmse(actual: pd.Series, predicted: np.ndarray) -> float:
    difference = np.asarray(actual, dtype=float) - predicted
    return float(np.sqrt(np.mean(difference**2)))


def seasonal_baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Mean occupancy for the same region and month across training years.

    Falls back to the region's own mean, then the overall mean, so a
    region-month never seen in training still gets a number instead of a NaN.
    """
    by_region_month = train.groupby([REGION, "month"], observed=True)[TARGET].mean()
    by_region = train.groupby(REGION, observed=True)[TARGET].mean()
    overall = float(train[TARGET].mean())

    predictions = []
    for _, row in test.iterrows():
        key = (row[REGION], row["month"])
        if key in by_region_month.index:
            predictions.append(float(by_region_month.loc[key]))
        elif row[REGION] in by_region.index:
            predictions.append(float(by_region.loc[row[REGION]]))
        else:
            predictions.append(overall)
    return np.asarray(predictions, dtype=float)


def compare(
    booster: lgb.Booster,
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, float | bool]:
    """Both sets of numbers, measured on the same held-out rows."""
    model_predictions = booster.predict(test[feature_columns])
    baseline_predictions = seasonal_baseline(train, test)

    model_mae = mae(test[TARGET], model_predictions)
    baseline_mae = mae(test[TARGET], baseline_predictions)

    return {
        "model_mae": model_mae,
        "model_rmse": rmse(test[TARGET], model_predictions),
        "baseline_mae": baseline_mae,
        "baseline_rmse": rmse(test[TARGET], baseline_predictions),
        "beat_baseline": model_mae < baseline_mae,
        "difference": baseline_mae - model_mae,
    }


def _verdict(results: dict[str, float | bool]) -> str:
    """The honest sentence, either way."""
    difference = abs(float(results["difference"]))
    if results["beat_baseline"]:
        return (
            f"**Yes.** The model's MAE is {difference:.2f} points lower than "
            "the seasonal average."
        )
    if difference == 0:
        return (
            "**No.** The model and the seasonal average are level. The extra "
            "complexity buys nothing."
        )
    return (
        f"**No.** The model's MAE is {difference:.2f} points *worse* than the "
        "seasonal average. The simple baseline is the better predictor on this "
        "data, and the demo should say so."
    )


def write_model_card(
    results: dict[str, float | bool],
    history: pd.DataFrame,
    train: pd.DataFrame,
    test: pd.DataFrame,
    test_year: int,
    covered: int,
) -> str:
    first = history.sort_values(["year", "month"]).iloc[0]
    last = history.sort_values(["year", "month"]).iloc[-1]
    short_series = covered < MIN_MONTHS

    features_list = "\n".join(
        f"| `{name}` | {description} |"
        for name, description in [
            ("month", "Calendar month, 1-12."),
            (
                "month_sin, month_cos",
                "Month as a cycle, so December sits next to January.",
            ),
            ("is_peak_season", "1 for December-March and July-August."),
            ("occupancy_lag_1", "Occupancy one month earlier."),
            ("occupancy_lag_2", "Occupancy two months earlier."),
            ("occupancy_lag_12", "Occupancy in the same month last year."),
            ("occupancy_rolling_3", "Mean of the three months before this one."),
            ("arrivals_trend", "Change in arrivals between the two previous months."),
            ("region", "Which region, treated as a category."),
        ]
    )

    warning = ""
    if short_series:
        warning = (
            f"\n> **Short series.** This model was trained on {covered} months "
            f"of history, fewer than the {MIN_MONTHS} months it wants. Treat "
            "every number below as a demonstration that the pipeline works, "
            "not as a forecast anyone should plan around.\n"
        )

    # Pulled out so the markdown table rows below stay readable.
    start = f"{int(first['year'])}-{int(first['month']):02d}"
    end = f"{int(last['year'])}-{int(last['month']):02d}"
    regions = history[REGION].nunique()
    usable_rows = len(train) + len(test)
    last_train_year = int(train["year"].max())
    model_mae = f"{results['model_mae']:.2f}"
    model_rmse = f"{results['model_rmse']:.2f}"
    base_mae = f"{results['baseline_mae']:.2f}"
    base_rmse = f"{results['baseline_rmse']:.2f}"
    months_note = f", which is below the {MIN_MONTHS} this model wants." if (
        short_series
    ) else "."

    card = f"""# Model card: {MODEL_VERSION}

Generated by `python ml/evaluate.py` on {date.today().isoformat()}.
Do not edit by hand; re-run the script instead.
{warning}
## What it predicts

A **region's** occupancy rate for a given calendar month, as a number from 0
to 100. That number is the visitor pressure figure behind the traffic-light
band on `GET /api/risk/{{id}}`.

## Data

| | |
|---|---|
| Source | `region_pressure_history`, loaded from SLTDA monthly figures |
| Date range | {start} to {end} |
| Months covered | {covered} |
| Regions | {regions} |
| Rows with a complete feature set | {usable_rows} |
| Training rows | {len(train)} (up to {last_train_year}) |
| Held-out rows | {len(test)} (all of {test_year}) |

The split is by time, never at random. The most recent full calendar year is
held out and the model never sees it during training. A random split would let
the model learn from months that come after the ones it is tested on, which
would make the numbers below meaningless.

## Features

| Feature | What it is |
|---|---|
{features_list}

Every feature is known before the month being predicted starts. The current
month's arrivals and guest nights are deliberately not used: in a real
forecast they have not happened yet.

## Results on the held-out year ({test_year})

| | MAE | RMSE |
|---|---|---|
| LightGBM model | **{model_mae}** | {model_rmse} |
| Seasonal average baseline | **{base_mae}** | {base_rmse} |

Both are in occupancy-rate points. The baseline predicts the mean occupancy
for that region and month across the training years.

### Did the model beat the baseline?

{_verdict(results)}

Hyperparameters were fixed before evaluation and were not adjusted after
seeing these numbers.

## Limitations

- **Pressure is regional, not per-site.** SLTDA publishes occupancy by
  province. Every destination in a region gets that region's figure. The data
  does not support a claim about any single site, and the API says so in its
  response.
- **Trained on {covered} months of data**{months_note}
- The model has never seen a shock. Nothing in the training window teaches it
  what a closure, a security incident or a fuel crisis does to occupancy.
- Arrivals and guest nights are used only as history. The model cannot react
  to a booking surge in the month it is predicting.
- Regions absent from training fall back to the overall mean, which will be
  wrong for anywhere unusual.
"""
    CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARD_PATH.write_text(card)
    return card


def main() -> int:
    if not MODEL_PATH.exists() or not FEATURES_PATH.exists():
        print(
            f"No model at {MODEL_PATH}. Run `python ml/train_pressure.py` first.",
            file=sys.stderr,
        )
        return 1

    metadata = json.loads(FEATURES_PATH.read_text())
    booster = lgb.Booster(model_file=str(MODEL_PATH))

    history = read_history()
    if history.empty:
        print("region_pressure_history is empty.", file=sys.stderr)
        return 1

    covered = months_covered(history)
    usable = model_frame(build_features(history))
    usable = as_categorical(usable, metadata["region_categories"])

    try:
        train, test, test_year = time_split(usable)
    except InsufficientData as exc:
        print(f"Cannot split the data: {exc}", file=sys.stderr)
        return 1

    results = compare(booster, train, test, metadata["features"])
    write_model_card(results, history, train, test, test_year, covered)

    print(f"Evaluated {MODEL_VERSION} on {test_year} ({len(test)} rows).")
    print(f"  model MAE             {results['model_mae']:>8.2f}")
    print(f"  model RMSE            {results['model_rmse']:>8.2f}")
    print(f"  baseline MAE          {results['baseline_mae']:>8.2f}")
    print(f"  baseline RMSE         {results['baseline_rmse']:>8.2f}")
    print()
    if results["beat_baseline"]:
        print(f"  Model beat the baseline by {results['difference']:.2f} MAE.")
    else:
        print(
            f"  Model LOST to the baseline by "
            f"{abs(float(results['difference'])):.2f} MAE. "
            "This is recorded in the card as-is."
        )
    print(f"  card                  {CARD_PATH}")
    return 0


__all__ = [
    "NUMERIC_FEATURES",
    "compare",
    "mae",
    "rmse",
    "seasonal_baseline",
    "write_model_card",
]


if __name__ == "__main__":
    raise SystemExit(main())
