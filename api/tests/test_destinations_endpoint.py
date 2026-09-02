"""GET /api/destinations and GET /api/destinations/{id} against real data.

The band on a marker has to be the same band the risk screen shows, or the
map is lying about which places are busy. That is what most of these check.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination, DestinationFactor
from api.schemas.common import Envelope
from api.schemas.destinations import DestinationDetail, DestinationListData

# One per region the synthetic history covers, so every one can be banded.
SEEDED = [
    ("Belihuloya", "Sabaragamuwa", "mountain", 6.7167, 80.7833),
    ("Meemure", "Central", "forest", 7.3833, 80.8333),
    ("Ella", "Uva", "mountain", 6.8667, 81.0466),
]

FACTOR_VALUES = {
    "environmental": 92.0,
    "community": 88.0,
    "crowd": 91.0,
    "infrastructure": 76.0,
    "suitability": 90.0,
}


@pytest.fixture
def seeded(forecast_ready: Session, empty_destinations: Session) -> list[int]:
    ids = []
    for name, region, landscape, lat, lon in SEEDED:
        destination = Destination(
            name=name,
            lat=lat,
            lon=lon,
            district="Ratnapura",
            region=region,
            landscape_type=landscape,
            activities=["hiking", "waterfalls"],
            cost_band="low",
            typical_days=3,
        )
        empty_destinations.add(destination)
        empty_destinations.flush()
        empty_destinations.add(
            DestinationFactor(
                destination_id=destination.id,
                **FACTOR_VALUES,
                source_ref="SLTDA 2024 table 4.2",
                confidence="measured",
            )
        )
        empty_destinations.flush()
        ids.append(int(destination.id))
    return ids


def test_count_matches_the_seeded_table_exactly(
    seeded: list[int], db_session: Session, db_client: TestClient
) -> None:
    response = db_client.get("/api/destinations")
    assert response.status_code == 200

    body = response.json()
    Envelope[DestinationListData].model_validate(body)

    returned = body["data"]["destinations"]
    assert len(returned) == len(seeded)
    assert len(returned) == db_session.query(Destination).count()
    assert [row["id"] for row in returned] == seeded


def test_list_returns_exactly_the_agreed_fields(
    seeded: list[int], db_client: TestClient
) -> None:
    row = db_client.get("/api/destinations").json()["data"]["destinations"][0]
    assert set(row) == {
        "id",
        "name",
        "lat",
        "lon",
        "district",
        "region",
        "sustainability_score",
        "band",
    }


def test_coordinates_come_back_unchanged(
    seeded: list[int], db_client: TestClient
) -> None:
    """features.md F7: all destinations appear at correct coordinates."""
    returned = db_client.get("/api/destinations").json()["data"]["destinations"]
    by_name = {row["name"]: row for row in returned}

    for name, region, _, lat, lon in SEEDED:
        assert by_name[name]["lat"] == pytest.approx(lat)
        assert by_name[name]["lon"] == pytest.approx(lon)
        assert by_name[name]["region"] == region


def test_bands_match_what_risk_returns_for_the_same_month(
    seeded: list[int], db_client: TestClient
) -> None:
    """A marker colour must never disagree with the risk screen."""
    month = date.today().month
    returned = db_client.get("/api/destinations").json()["data"]["destinations"]

    for row in returned:
        risk = db_client.get(
            f"/api/risk/{row['id']}", params={"month": month}
        ).json()["data"]
        assert row["band"] == risk["band"], row["name"]


def test_detail_band_matches_the_list_band(
    seeded: list[int], db_client: TestClient
) -> None:
    listed = db_client.get("/api/destinations").json()["data"]["destinations"]
    for row in listed:
        detail = db_client.get(f"/api/destinations/{row['id']}").json()["data"]
        assert detail["band"] == row["band"]
        assert detail["sustainability_score"] == row["sustainability_score"]


def test_detail_adds_the_agreed_fields(
    seeded: list[int], db_client: TestClient
) -> None:
    response = db_client.get(f"/api/destinations/{seeded[0]}")
    assert response.status_code == 200

    body = response.json()
    Envelope[DestinationDetail].model_validate(body)

    data = body["data"]
    assert data["id"] == seeded[0]
    assert data["activities"] == ["hiking", "waterfalls"]
    assert data["cost_band"] == "low"
    assert data["typical_days"] == 3
    assert data["source_ref"] == "SLTDA 2024 table 4.2"
    assert data["confidence"] == "measured"
    assert data["factors"] == {
        "environmental": 92,
        "community": 88,
        "crowd": 91,
        "infrastructure": 76,
        "suitability": 90,
    }


def test_detail_is_the_summary_plus_six_fields(
    seeded: list[int], db_client: TestClient
) -> None:
    listed = db_client.get("/api/destinations").json()["data"]["destinations"][0]
    detail = db_client.get(f"/api/destinations/{seeded[0]}").json()["data"]

    assert set(detail) - set(listed) == {
        "factors",
        "confidence",
        "activities",
        "cost_band",
        "typical_days",
        "source_ref",
    }
    # And the shared fields agree.
    for field in listed:
        assert detail[field] == listed[field]


def test_unknown_id_returns_404(seeded: list[int], db_client: TestClient) -> None:
    response = db_client.get("/api/destinations/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "404"
    assert "999999" in body["error"]["message"]


def test_empty_table_returns_an_empty_list_not_an_error(
    forecast_ready: Session, empty_destinations: Session, db_client: TestClient
) -> None:
    response = db_client.get("/api/destinations")
    assert response.status_code == 200
    assert response.json()["data"]["destinations"] == []


def test_destination_without_factors_returns_503(
    forecast_ready: Session, empty_destinations: Session, db_client: TestClient
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

    assert db_client.get("/api/destinations").status_code == 503
    assert db_client.get(f"/api/destinations/{destination.id}").status_code == 503


def test_untrained_model_returns_503(
    empty_destinations: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Without a model there is no band, and a marker needs one."""
    from api.services import forecast as forecast_service

    destination = Destination(
        name="Belihuloya",
        lat=6.7,
        lon=80.8,
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
            **FACTOR_VALUES,
            source_ref="test",
            confidence="measured",
        )
    )
    empty_destinations.flush()

    monkeypatch.setattr(forecast_service, "MODEL_PATH", tmp_path / "missing.txt")
    monkeypatch.setattr(forecast_service, "FEATURES_PATH", tmp_path / "gone.json")
    forecast_service.clear_cache()

    response = db_client.get("/api/destinations")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "forecast_unavailable"
    forecast_service.clear_cache()
