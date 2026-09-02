"""Train the visitor pressure model.

    python ml/train_pressure.py

Reads region_pressure_history from the database, builds features, holds out
the most recent full year, trains a LightGBM regressor, and saves the model
plus the exact feature list it was trained on.

Run ml/evaluate.py afterwards to produce the model card. Training deliberately
does not report its own accuracy: the number that matters is the one measured
on the held-out year, and keeping the two steps apart makes it harder to
quietly tune against the test set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Lets the script run as `python ml/train_pressure.py` from the repo root,
# which is how features.md F4 asks for it. `python -m ml.train_pressure` also
# works.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lightgbm as lgb  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import select  # noqa: E402

from api.database import SessionLocal  # noqa: E402
from api.models import RegionPressureHistory  # noqa: E402
from ml.features import (  # noqa: E402
    FEATURE_COLUMNS,
    MIN_MONTHS,
    REGION,
    TARGET,
    InsufficientData,
    as_categorical,
    build_features,
    model_frame,
    months_covered,
    time_split,
)

MODEL_VERSION = "pressure-v1.0"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / f"{MODEL_VERSION}.txt"
FEATURES_PATH = ARTIFACTS_DIR / f"{MODEL_VERSION}.features.json"

# Fixed up front, not tuned against the held-out year. Retuning until the
# model beats the baseline would make the comparison in the model card
# meaningless (features.md F4).
PARAMS = {
    "objective": "regression",
    "metric": "l1",
    "learning_rate": 0.05,
    "num_leaves": 15,
    # The series is short, so the defaults would refuse to split at all.
    "min_data_in_leaf": 5,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "verbose": -1,
    "seed": 42,
}
NUM_BOOST_ROUND = 300


def read_history() -> pd.DataFrame:
    """Every row of region_pressure_history, as a dataframe."""
    session = SessionLocal()
    try:
        rows = session.execute(select(RegionPressureHistory)).scalars().all()
    finally:
        session.close()

    return pd.DataFrame(
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


def warn_if_series_is_short(history: pd.DataFrame) -> int:
    """Print a loud warning when there is not much history. Returns the count."""
    covered = months_covered(history)
    if covered < MIN_MONTHS:
        line = "!" * 72
        print(line, file=sys.stderr)
        print(
            f"WARNING: only {covered} months of history "
            f"(fewer than the {MIN_MONTHS} this model wants).",
            file=sys.stderr,
        )
        print(
            "Anything trained on this is a demonstration, not a forecast. "
            "The model card will say so.",
            file=sys.stderr,
        )
        print(line, file=sys.stderr)
    return covered


def train_model(
    train: pd.DataFrame, feature_columns: list[str] | None = None
) -> lgb.Booster:
    """Fit the regressor. Kept separate from main so tests can call it."""
    columns = feature_columns or FEATURE_COLUMNS
    dataset = lgb.Dataset(
        train[columns],
        label=train[TARGET],
        categorical_feature=[REGION],
        free_raw_data=False,
    )
    return lgb.train(PARAMS, dataset, num_boost_round=NUM_BOOST_ROUND)


def save(booster: lgb.Booster, categories: list[str], test_year: int) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(MODEL_PATH))

    # The feature order and the region category order both have to match at
    # inference time, so they travel with the model rather than being
    # rebuilt from whatever the database happens to hold later.
    FEATURES_PATH.write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "features": FEATURE_COLUMNS,
                "categorical_features": [REGION],
                "region_categories": categories,
                "target": TARGET,
                "test_year": test_year,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    history = read_history()
    if history.empty:
        print(
            "region_pressure_history is empty. Load the dataset first with "
            "`python -m ml.seed`.",
            file=sys.stderr,
        )
        return 1

    warn_if_series_is_short(history)

    features = build_features(history)
    usable = model_frame(features)

    if usable.empty:
        print(
            "No row has a complete set of features. Each region needs at "
            "least 13 consecutive months before the lag-12 feature exists.",
            file=sys.stderr,
        )
        return 1

    categories = sorted(usable[REGION].astype(str).unique())
    usable = as_categorical(usable, categories)

    try:
        train, test, test_year = time_split(usable)
    except InsufficientData as exc:
        print(f"Cannot split the data: {exc}", file=sys.stderr)
        return 1

    booster = train_model(train)
    save(booster, categories, test_year)

    print(f"Trained {MODEL_VERSION}.")
    print(f"  history months        {months_covered(history):>5}")
    print(f"  usable rows           {len(usable):>5}")
    print(f"  training rows         {len(train):>5}  (up to {train['year'].max()})")
    print(f"  held-out rows         {len(test):>5}  ({test_year})")
    print(f"  regions               {len(categories):>5}")
    print(f"  model                 {MODEL_PATH}")
    print(f"  features              {FEATURES_PATH}")
    print()
    print("Now run `python ml/evaluate.py` to measure it and write the card.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
