"""POST /api/simulate against real stored factor values.

The properties here are the ones a judge can check by moving a slider: the
score stays in range, it moves the sensible way, and putting the sliders back
gives the original number.
"""

import itertools
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination, DestinationFactor
from api.routers.simulate import WARNING_THRESHOLD, apply_sliders
from api.schemas.common import Envelope
from api.schemas.simulate import SimulateData

# Integers, as the dataset uses. See test_reset_is_exact for why that matters.
STORED = {
    "environmental": 80,
    "community": 70,
    "crowd": 60,
    "infrastructure": 50,
    "suitability": 40,
}


@pytest.fixture
def destination_id(empty_destinations: Session) -> int:
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
    empty_destinations.add(destination)
    empty_destinations.flush()
    empty_destinations.add(
        DestinationFactor(
            destination_id=destination.id,
            **{name: float(value) for name, value in STORED.items()},
            source_ref="test fixture",
            confidence="measured",
        )
    )
    empty_destinations.flush()
    return int(destination.id)


def body(
    tourists: int = 40, waste: int = 80, infrastructure: int = 50
) -> dict[str, int]:
    return {
        "expected_tourists": tourists,
        "waste_management_level": waste,
        "infrastructure_level": infrastructure,
    }


def simulate(client: TestClient, destination_id: int, **sliders: int) -> dict:
    response = client.post(
        "/api/simulate", json={"destination_id": destination_id, **body(**sliders)}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_returns_the_contract_shape(
    db_client: TestClient, destination_id: int
) -> None:
    response = db_client.post(
        "/api/simulate", json={"destination_id": destination_id, **body()}
    )
    assert response.status_code == 200
    Envelope[SimulateData].model_validate(response.json())

    data = response.json()["data"]
    assert data["destination_id"] == destination_id
    assert len(data["contributions"]) == 5
    assert all(item["type"] == "exact" for item in data["contributions"])
    assert sum(item["percent"] for item in data["contributions"]) == 100


@pytest.mark.parametrize(
    ("tourists", "waste", "infrastructure"),
    list(itertools.product([0, 100], repeat=3)),
)
def test_score_stays_in_range_at_every_corner(
    db_client: TestClient,
    destination_id: int,
    tourists: int,
    waste: int,
    infrastructure: int,
) -> None:
    """features.md F6: test the corners. All eight of them."""
    data = simulate(
        db_client,
        destination_id,
        tourists=tourists,
        waste=waste,
        infrastructure=infrastructure,
    )

    assert 0 <= data["sustainability_score"] <= 100
    assert 0 <= data["baseline_score"] <= 100
    assert -100 <= data["delta"] <= 100
    for value in data["factors"].values():
        assert 0 <= value <= 100


def test_more_tourists_never_raises_the_score(
    db_client: TestClient, destination_id: int
) -> None:
    """Direction has to be sensible or the simulator is lying."""
    previous = 101
    for tourists in range(0, 101, 10):
        data = simulate(db_client, destination_id, tourists=tourists)
        assert data["sustainability_score"] <= previous
        previous = data["sustainability_score"]


def test_better_waste_management_never_lowers_the_score(
    db_client: TestClient, destination_id: int
) -> None:
    previous = -1
    for waste in range(0, 101, 10):
        data = simulate(db_client, destination_id, waste=waste)
        assert data["sustainability_score"] >= previous
        previous = data["sustainability_score"]


def test_better_infrastructure_never_lowers_the_score(
    db_client: TestClient, destination_id: int
) -> None:
    previous = -1
    for level in range(0, 101, 10):
        data = simulate(db_client, destination_id, infrastructure=level)
        assert data["sustainability_score"] >= previous
        previous = data["sustainability_score"]


def test_reset_returns_the_original_score_exactly(
    db_client: TestClient, destination_id: int
) -> None:
    """features.md F6: resetting the sliders returns exactly the original.

    The reset position for crowd is 100 - stored_crowd, because the slider is
    "how busy" and the factor scores "how uncrowded".
    """
    data = simulate(
        db_client,
        destination_id,
        tourists=100 - STORED["crowd"],
        waste=STORED["environmental"],
        infrastructure=STORED["infrastructure"],
    )

    assert data["sustainability_score"] == data["baseline_score"]
    assert data["delta"] == 0
    assert data["warning"] is None
    # And the factor values came back untouched.
    for name, value in STORED.items():
        assert data["factors"][name] == value


def test_delta_is_new_minus_original(
    db_client: TestClient, destination_id: int
) -> None:
    data = simulate(db_client, destination_id, tourists=90, waste=10)
    assert data["delta"] == (
        data["sustainability_score"] - data["baseline_score"]
    )
    assert data["delta"] < 0


def test_improving_everything_gives_a_positive_delta(
    db_client: TestClient, destination_id: int
) -> None:
    data = simulate(
        db_client, destination_id, tourists=0, waste=100, infrastructure=100
    )
    assert data["delta"] > 0
    assert data["warning"] is None


def test_warning_appears_only_on_a_big_drop(
    db_client: TestClient, destination_id: int
) -> None:
    """F6: warning when the change costs more than ten points."""
    bad = simulate(db_client, destination_id, tourists=100, waste=0)
    assert bad["delta"] < -WARNING_THRESHOLD
    assert bad["warning"] is not None
    assert str(abs(bad["delta"])) in bad["warning"]

    unchanged = simulate(
        db_client,
        destination_id,
        tourists=100 - STORED["crowd"],
        waste=STORED["environmental"],
        infrastructure=STORED["infrastructure"],
    )
    assert unchanged["warning"] is None


def test_community_and_suitability_are_never_touched(
    db_client: TestClient, destination_id: int
) -> None:
    """No slider claims to move these, so they must not move."""
    data = simulate(db_client, destination_id, tourists=100, waste=0)
    assert data["factors"]["community"] == STORED["community"]
    assert data["factors"]["suitability"] == STORED["suitability"]


def test_apply_sliders_maps_the_three_factors() -> None:
    stored = {name: float(value) for name, value in STORED.items()}
    adjusted = apply_sliders(stored, 30, 90, 45)

    assert adjusted["crowd"] == 70.0
    assert adjusted["environmental"] == 90.0
    assert adjusted["infrastructure"] == 45.0
    # Untouched.
    assert adjusted["community"] == stored["community"]
    assert adjusted["suitability"] == stored["suitability"]
    # The input dictionary is not modified in place.
    assert stored["crowd"] == float(STORED["crowd"])


def test_unknown_destination_returns_404(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/simulate", json={"destination_id": 999999, **body()}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "404"


def test_destination_without_factors_returns_503(
    empty_destinations: Session, db_client: TestClient
) -> None:
    destination = Destination(
        name="NoFactors",
        lat=6.9,
        lon=80.8,
        district="Kandy",
        region="Central",
        landscape_type="forest",
        activities=["hiking"],
        cost_band="low",
        typical_days=2,
    )
    empty_destinations.add(destination)
    empty_destinations.flush()

    response = db_client.post(
        "/api/simulate", json={"destination_id": destination.id, **body()}
    )
    assert response.status_code == 503


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_tourists": 101},
        {"expected_tourists": -1},
        {"waste_management_level": 101},
        {"infrastructure_level": -5},
    ],
)
def test_out_of_range_slider_returns_422(
    db_client: TestClient, destination_id: int, payload: dict
) -> None:
    response = db_client.post(
        "/api/simulate",
        json={"destination_id": destination_id, **body(), **payload},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_responds_in_under_300ms(
    db_client: TestClient, destination_id: int
) -> None:
    """features.md F6: the score updates within 300ms of a slider moving."""
    started = time.perf_counter()
    response = db_client.post(
        "/api/simulate", json={"destination_id": destination_id, **body()}
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 0.3, f"took {elapsed:.3f}s"
