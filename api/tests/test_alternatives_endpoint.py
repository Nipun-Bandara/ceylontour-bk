"""GET /api/alternatives/{id} against real forecasts.

The synthetic history in conftest gives the three regions clearly different
pressure levels: Sabaragamuwa lowest, then Central, then Uva. That is what
makes "strictly lower pressure" testable without guessing at model output.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination
from api.schemas.alternatives import AlternativesData
from api.schemas.common import Envelope
from api.services.similarity import NO_MATCH_MESSAGE


@pytest.fixture
def alternatives_client(
    forecast_ready: Session, empty_destinations: Session, db_client: TestClient
) -> Iterator[TestClient]:
    yield db_client


def add(
    session: Session,
    name: str,
    region: str,
    *,
    landscape_type: str = "mountain",
    activities: list[str] | None = None,
    cost_band: str = "low",
    typical_days: int = 3,
    lat: float = 6.9,
    lon: float = 80.8,
) -> Destination:
    destination = Destination(
        name=name,
        lat=lat,
        lon=lon,
        district="Ratnapura",
        region=region,
        landscape_type=landscape_type,
        activities=activities or ["hiking"],
        cost_band=cost_band,
        typical_days=typical_days,
    )
    session.add(destination)
    session.flush()
    return destination


def test_all_alternatives_have_lower_pressure_than_the_source(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    source = add(forecast_ready, "Crowded", "Uva")
    add(forecast_ready, "Quiet One", "Sabaragamuwa")
    add(forecast_ready, "Quiet Two", "Sabaragamuwa", lat=7.1, lon=80.9)
    add(forecast_ready, "Middling", "Central", lat=7.3, lon=80.6)

    response = alternatives_client.get(f"/api/alternatives/{source.id}")
    assert response.status_code == 200

    body = response.json()
    Envelope[AlternativesData].model_validate(body)

    data = body["data"]
    assert data["destination_id"] == source.id
    assert data["alternatives"]
    assert data["message"] is None

    # The endpoint compares pressure for the current month, so ask the risk
    # endpoint for the same month to get the figure it used.
    source_pressure = alternatives_client.get(
        f"/api/risk/{source.id}", params={"month": date.today().month}
    ).json()["data"]["predicted_pressure"]

    for alternative in data["alternatives"]:
        assert alternative["predicted_pressure"] < source_pressure
        assert 0 <= alternative["similarity_percent"] <= 100
        assert alternative["reason"].startswith("Similar ")
        assert alternative["reason"].endswith(".")


def test_never_returns_more_than_three(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    source = add(forecast_ready, "Crowded", "Uva")
    for number in range(6):
        add(
            forecast_ready,
            f"Quiet {number}",
            "Sabaragamuwa",
            lat=6.5 + number * 0.1,
            lon=80.5 + number * 0.1,
        )

    body = alternatives_client.get(f"/api/alternatives/{source.id}").json()
    assert len(body["data"]["alternatives"]) == 3


def test_ranked_by_similarity(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    source = add(
        forecast_ready,
        "Crowded",
        "Uva",
        landscape_type="mountain",
        activities=["hiking", "waterfalls"],
    )
    # Same landscape and activities, so a close match.
    add(
        forecast_ready,
        "Twin",
        "Sabaragamuwa",
        landscape_type="mountain",
        activities=["hiking", "waterfalls"],
    )
    # Nothing in common but the region's lower pressure.
    add(
        forecast_ready,
        "Different",
        "Sabaragamuwa",
        landscape_type="beach",
        activities=["surfing"],
        lat=6.0,
        lon=81.0,
    )

    alternatives = alternatives_client.get(
        f"/api/alternatives/{source.id}"
    ).json()["data"]["alternatives"]

    assert [item["name"] for item in alternatives] == ["Twin", "Different"]
    percents = [item["similarity_percent"] for item in alternatives]
    assert percents == sorted(percents, reverse=True)
    assert alternatives[0]["similarity_percent"] > alternatives[1][
        "similarity_percent"
    ]


def test_empty_case_returns_200_and_a_message(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    """features.md F5: say so rather than returning a bad match."""
    # The quietest region, so nothing can be lower.
    source = add(forecast_ready, "Already Quiet", "Sabaragamuwa")
    add(forecast_ready, "Busier", "Uva", lat=7.0, lon=81.0)

    response = alternatives_client.get(f"/api/alternatives/{source.id}")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["alternatives"] == []
    assert data["message"] == NO_MATCH_MESSAGE


def test_budget_filter_is_respected(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    """An alternative must never break the user's original filters."""
    source = add(forecast_ready, "Crowded", "Uva")
    add(forecast_ready, "Cheap", "Sabaragamuwa", cost_band="low")
    add(
        forecast_ready,
        "Pricey",
        "Sabaragamuwa",
        cost_band="high",
        lat=7.0,
        lon=80.9,
    )

    without = alternatives_client.get(f"/api/alternatives/{source.id}").json()
    assert {item["name"] for item in without["data"]["alternatives"]} == {
        "Cheap",
        "Pricey",
    }

    # 20000 covers the low band but not the high one.
    with_budget = alternatives_client.get(
        f"/api/alternatives/{source.id}", params={"budget_lkr": 20000}
    ).json()
    assert [item["name"] for item in with_budget["data"]["alternatives"]] == [
        "Cheap"
    ]


def test_duration_filter_is_respected(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    source = add(forecast_ready, "Crowded", "Uva")
    add(forecast_ready, "Short", "Sabaragamuwa", typical_days=2)
    add(
        forecast_ready,
        "Long",
        "Sabaragamuwa",
        typical_days=10,
        lat=7.0,
        lon=80.9,
    )

    body = alternatives_client.get(
        f"/api/alternatives/{source.id}", params={"duration_days": 3}
    ).json()
    assert [item["name"] for item in body["data"]["alternatives"]] == ["Short"]


def test_filters_can_empty_the_list(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    """A filter that excludes everything gives the message, not a bad match."""
    source = add(forecast_ready, "Crowded", "Uva")
    add(forecast_ready, "Pricey", "Sabaragamuwa", cost_band="high")

    body = alternatives_client.get(
        f"/api/alternatives/{source.id}", params={"budget_lkr": 20000}
    ).json()
    assert body["data"]["alternatives"] == []
    assert body["data"]["message"] == NO_MATCH_MESSAGE


def test_a_destination_is_never_its_own_alternative(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    source = add(forecast_ready, "Crowded", "Uva")
    add(forecast_ready, "Quiet", "Sabaragamuwa")

    body = alternatives_client.get(f"/api/alternatives/{source.id}").json()
    returned = {item["destination_id"] for item in body["data"]["alternatives"]}
    assert source.id not in returned


def test_same_region_is_never_lower_pressure_than_itself(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    """Two destinations in one region share a forecast, so neither is lower."""
    source = add(forecast_ready, "One", "Uva")
    add(forecast_ready, "Two", "Uva", lat=7.0, lon=81.0)

    body = alternatives_client.get(f"/api/alternatives/{source.id}").json()
    assert body["data"]["alternatives"] == []


def test_unknown_id_returns_404(alternatives_client: TestClient) -> None:
    response = alternatives_client.get("/api/alternatives/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "404"


def test_negative_budget_returns_422(
    forecast_ready: Session,
    empty_destinations: Session,
    alternatives_client: TestClient,
) -> None:
    source = add(forecast_ready, "Crowded", "Uva")
    response = alternatives_client.get(
        f"/api/alternatives/{source.id}", params={"budget_lkr": -1}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
