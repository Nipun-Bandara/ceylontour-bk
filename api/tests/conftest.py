"""Shared test fixtures.

Most tests need no database: the routers other than /api/recommend return
mocks, and the index is pure arithmetic. The recommend tests do need Postgres,
so they use db_client, which runs each test inside a transaction that is
rolled back afterwards. Nothing a test inserts survives it.
"""

import json
import math
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api import rate_limit
from api.database import engine, get_db
from api.main import app
from api.models import RegionPressureHistory
from api.services import forecast as forecast_service
from ml.features import (
    FEATURE_COLUMNS,
    PEAK_SEASON_MONTHS,
    REGION,
    as_categorical,
    build_features,
    model_frame,
    time_split,
)
from ml.train_pressure import train_model

# Regions the synthetic series covers. Anything needing a forecast has to sit
# in one of these.
SYNTHETIC_REGIONS = ["Sabaragamuwa", "Central", "Uva"]
SYNTHETIC_YEARS = range(2020, 2025)


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> Iterator[None]:
    """Every test starts with an empty rate-limit counter.

    Without this the suite's own traffic would eventually trip the limiter and
    fail an unrelated test, and the order tests ran in would start to matter.
    """
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A session inside a transaction that is always rolled back.

    Skips rather than fails when Postgres is not running, so `pytest` still
    works on a laptop with nothing started. Those tests are not optional
    though: run them with `docker compose exec api pytest` before merging.
    """
    try:
        connection = engine.connect()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"Postgres is not reachable, run inside docker compose: {exc}")

    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_client(db_session: Session) -> Iterator[TestClient]:
    """A client whose requests run against db_session's transaction."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def empty_destinations(db_session: Session) -> Session:
    """Remove any seeded rows so a test controls the whole dataset.

    Safe because the surrounding transaction is rolled back.
    """
    db_session.execute(text("DELETE FROM destination_factors"))
    db_session.execute(text("DELETE FROM destinations"))
    db_session.flush()
    return db_session


def synthetic_history_rows() -> list[dict]:
    """A believable monthly series, seasonal with a per-region level.

    Tests that need a forecast build their own history rather than depending
    on how much real SLTDA data has been collected so far. Every month of
    every year is present, so any month can be asked about.
    """
    rows = []
    for offset, region in enumerate(SYNTHETIC_REGIONS):
        for year in SYNTHETIC_YEARS:
            for month in range(1, 13):
                seasonal = 18 * math.sin(2 * math.pi * (month - 3) / 12)
                peak = 9 if month in PEAK_SEASON_MONTHS else 0
                occupancy = 40 + offset * 12 + seasonal + peak
                rows.append(
                    {
                        "region": region,
                        "year": year,
                        "month": month,
                        "occupancy_rate": round(float(occupancy), 2),
                        "arrivals": int(900 * (1 + occupancy / 100)),
                        "guest_nights": int(2100 * (1 + occupancy / 100)),
                    }
                )
    return rows


@pytest.fixture(scope="session")
def trained_artifacts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """A real LightGBM model, trained once per run into a temp directory.

    Nothing here reads ml/artifacts/, so these tests pass whether or not
    anyone has trained the committed model.
    """
    directory = tmp_path_factory.mktemp("artifacts")
    frame = model_frame(build_features(pd.DataFrame(synthetic_history_rows())))
    categories = sorted(frame[REGION].astype(str).unique())
    train, _, test_year = time_split(as_categorical(frame, categories))

    booster = train_model(train)
    model_path = directory / "pressure-test.txt"
    features_path = directory / "pressure-test.features.json"
    booster.save_model(str(model_path))
    features_path.write_text(
        json.dumps(
            {
                "model_version": "pressure-test-v1",
                "features": FEATURE_COLUMNS,
                "categorical_features": [REGION],
                "region_categories": categories,
                "target": "occupancy_rate",
                "test_year": test_year,
            }
        )
    )
    return {"model": model_path, "features": features_path}


@pytest.fixture
def forecast_ready(
    trained_artifacts: dict[str, Path],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Session]:
    """Point the forecast service at the test model and load its history.

    The model and every answer are cached for the life of the process, so the
    cache is cleared on both sides of the test or one test's model would leak
    into the next.
    """
    monkeypatch.setattr(forecast_service, "MODEL_PATH", trained_artifacts["model"])
    monkeypatch.setattr(
        forecast_service, "FEATURES_PATH", trained_artifacts["features"]
    )
    forecast_service.clear_cache()

    db_session.query(RegionPressureHistory).delete()
    for row in synthetic_history_rows():
        db_session.add(RegionPressureHistory(**row))
    db_session.flush()

    yield db_session

    forecast_service.clear_cache()
