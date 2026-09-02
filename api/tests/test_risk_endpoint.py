"""GET /api/risk/{id}?month= against a real model and real history.

The model is trained once for the module into a temp directory, from the same
synthetic series that gets loaded into the database. Nothing here reads the
committed artefact, so these pass whether or not anyone has trained one.
"""

import json
import math
import time
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination, RegionPressureHistory
from api.schemas.common import Envelope
from api.schemas.risk import RiskData
from api.services import forecast as forecast_service
from ml.features import (
    PEAK_SEASON_MONTHS,
    REGION,
    as_categorical,
    build_features,
    model_frame,
    time_split,
)
from ml.train_pressure import FEATURE_COLUMNS, train_model

REGIONS = ["Sabaragamuwa", "Uva"]
YEARS = range(2020, 2025)


def synthetic_rows() -> list[dict]:
    """A believable monthly series. Kept here so these tests do not depend on
    how much real data has been collected yet."""
    rows = []
    for offset, region in enumerate(REGIONS):
        for year in YEARS:
            for month in range(1, 13):
                seasonal = 18 * math.sin(2 * math.pi * (month - 3) / 12)
                peak = 9 if month in PEAK_SEASON_MONTHS else 0
                occupancy = 45 + offset * 8 + seasonal + peak
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


@pytest.fixture(scope="module")
def trained_artifacts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Train a real LightGBM model once, into a temp directory."""
    directory = tmp_path_factory.mktemp("artifacts")
    frame = model_frame(build_features(pd.DataFrame(synthetic_rows())))
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
def risk_client(
    trained_artifacts: dict[str, Path],
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """A client pointed at the temp model, with history and a destination."""
    monkeypatch.setattr(forecast_service, "MODEL_PATH", trained_artifacts["model"])
    monkeypatch.setattr(
        forecast_service, "FEATURES_PATH", trained_artifacts["features"]
    )
    # The model is cached for the process, so it has to be dropped between
    # tests or the first test's model would leak into the rest.
    forecast_service.clear_cache()

    db_session.query(RegionPressureHistory).delete()
    for row in synthetic_rows():
        db_session.add(RegionPressureHistory(**row))
    db_session.flush()

    yield db_client

    forecast_service.clear_cache()


@pytest.fixture
def destination_id(db_session: Session) -> int:
    destination = Destination(
        name="Belihuloya",
        lat=6.7167,
        lon=80.7833,
        district="Ratnapura",
        region="Sabaragamuwa",
        landscape_type="mountain",
        activities=["hiking"],
        cost_band="low",
        typical_days=3,
    )
    db_session.add(destination)
    db_session.flush()
    return int(destination.id)


def test_valid_id_returns_a_band_and_a_breakdown(
    risk_client: TestClient, destination_id: int
) -> None:
    response = risk_client.get(f"/api/risk/{destination_id}", params={"month": 9})
    assert response.status_code == 200

    body = response.json()
    Envelope[RiskData].model_validate(body)

    data = body["data"]
    assert data["destination_id"] == destination_id
    assert data["region"] == "Sabaragamuwa"
    assert data["month"] == 9
    assert data["band"] in {"low", "medium", "high"}
    assert 0 <= data["predicted_pressure"] <= 100
    assert data["scope"] == "regional indicator, not site-specific"

    assert 0 < len(data["contributions"]) <= 5
    assert sum(item["percent"] for item in data["contributions"]) == 100


def test_every_contribution_is_estimated(
    risk_client: TestClient, destination_id: int
) -> None:
    """SHAP values are a model's own attribution, never an exact calculation."""
    body = risk_client.get(
        f"/api/risk/{destination_id}", params={"month": 7}
    ).json()
    contributions = body["data"]["contributions"]

    assert contributions
    assert all(item["type"] == "estimated" for item in contributions)
    # And they read as English, not as column names.
    assert all("_" not in item["factor"] for item in contributions)


def test_breakdown_is_capped_at_five(
    risk_client: TestClient, destination_id: int
) -> None:
    body = risk_client.get(
        f"/api/risk/{destination_id}", params={"month": 1}
    ).json()
    assert len(body["data"]["contributions"]) <= 5


def test_meta_names_the_model_that_produced_the_number(
    risk_client: TestClient, destination_id: int
) -> None:
    body = risk_client.get(
        f"/api/risk/{destination_id}", params={"month": 9}
    ).json()
    assert body["meta"]["model_version"] == "pressure-test-v1"


def test_unknown_id_returns_404(risk_client: TestClient) -> None:
    response = risk_client.get("/api/risk/999999", params={"month": 9})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "404"
    assert "999999" in response.json()["error"]["message"]


def test_month_13_returns_422(risk_client: TestClient, destination_id: int) -> None:
    response = risk_client.get(f"/api/risk/{destination_id}", params={"month": 13})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_month_zero_returns_422(risk_client: TestClient, destination_id: int) -> None:
    response = risk_client.get(f"/api/risk/{destination_id}", params={"month": 0})
    assert response.status_code == 422


def test_inference_is_under_500ms(
    risk_client: TestClient, destination_id: int
) -> None:
    """features.md F4 acceptance criterion. Measured cold, before the cache."""
    started = time.perf_counter()
    response = risk_client.get(f"/api/risk/{destination_id}", params={"month": 4})
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 0.5, f"cold inference took {elapsed:.3f}s"


def test_repeat_requests_are_served_from_cache(
    risk_client: TestClient, destination_id: int
) -> None:
    first = risk_client.get(f"/api/risk/{destination_id}", params={"month": 4})

    started = time.perf_counter()
    second = risk_client.get(f"/api/risk/{destination_id}", params={"month": 4})
    elapsed = time.perf_counter() - started

    assert first.json()["data"] == second.json()["data"]
    assert elapsed < 0.5
    assert ("Sabaragamuwa", 4) in forecast_service._CACHE


def test_bands_come_from_config_not_from_the_function() -> None:
    bands = forecast_service.load_bands()
    assert [band["name"] for band in bands] == ["low", "medium", "high"]
    assert [band["colour"] for band in bands] == ["green", "yellow", "red"]

    # The boundaries the config declares: 0-40, 41-70, 71-100.
    assert forecast_service.band_for(0) == "low"
    assert forecast_service.band_for(40) == "low"
    assert forecast_service.band_for(40.5) == "medium"
    assert forecast_service.band_for(70) == "medium"
    assert forecast_service.band_for(70.1) == "high"
    assert forecast_service.band_for(100) == "high"


def test_untrained_model_returns_503_not_500(
    db_client: TestClient,
    destination_id: int,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No artefact yet is the state the repo is actually in today."""
    monkeypatch.setattr(forecast_service, "MODEL_PATH", tmp_path / "missing.txt")
    monkeypatch.setattr(
        forecast_service, "FEATURES_PATH", tmp_path / "missing.json"
    )
    forecast_service.clear_cache()

    response = db_client.get(f"/api/risk/{destination_id}", params={"month": 9})

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "forecast_unavailable"
    assert "train_pressure" in body["error"]["message"]
    forecast_service.clear_cache()


def test_region_with_too_little_history_returns_503(
    trained_artifacts: dict[str, Path],
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(forecast_service, "MODEL_PATH", trained_artifacts["model"])
    monkeypatch.setattr(
        forecast_service, "FEATURES_PATH", trained_artifacts["features"]
    )
    forecast_service.clear_cache()

    db_session.query(RegionPressureHistory).delete()
    destination = Destination(
        name="Nowhere",
        lat=7.0,
        lon=80.0,
        district="Kandy",
        region="Empty",
        landscape_type="forest",
        activities=["hiking"],
        cost_band="low",
        typical_days=2,
    )
    db_session.add(destination)
    db_session.flush()

    response = db_client.get(
        f"/api/risk/{destination.id}", params={"month": 9}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "forecast_unavailable"
    forecast_service.clear_cache()
