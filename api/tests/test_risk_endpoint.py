"""GET /api/risk/{id}?month= against a real model and real history.

The model and the synthetic series come from conftest, which trains once per
run into a temp directory. Nothing here reads the committed artefact, so these
pass whether or not anyone has trained one.
"""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination, RegionPressureHistory
from api.schemas.common import Envelope
from api.schemas.risk import RiskData
from api.services import forecast as forecast_service


@pytest.fixture
def risk_client(
    forecast_ready: Session, db_client: TestClient
) -> Iterator[TestClient]:
    yield db_client


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
    forecast_ready: Session, db_client: TestClient
) -> None:
    forecast_ready.query(RegionPressureHistory).delete()
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
    forecast_ready.add(destination)
    forecast_ready.flush()

    response = db_client.get(f"/api/risk/{destination.id}", params={"month": 9})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "forecast_unavailable"
