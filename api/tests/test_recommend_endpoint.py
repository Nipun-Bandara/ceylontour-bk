"""POST /api/recommend against real data.

These need Postgres. Each one runs inside a transaction that is rolled back,
so they build their own dataset and leave nothing behind.
"""

import time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination, DestinationFactor
from api.schemas.recommend import RecommendEnvelope

REQUEST = {
    "budget_lkr": 50000,
    "duration_days": 4,
    "interest": "nature",
    "crowd_preference": "low",
    "sustainability_weight": "high",
    "travel_month": 9,
}


def add_destination(
    session: Session,
    name: str,
    *,
    cost_band: str = "low",
    typical_days: int = 3,
    environmental: float = 80.0,
    confidence: str = "measured",
    with_factors: bool = True,
) -> Destination:
    destination = Destination(
        name=name,
        lat=6.9,
        lon=80.8,
        district="Ratnapura",
        region="Sabaragamuwa",
        landscape_type="mountain",
        activities=["hiking"],
        cost_band=cost_band,
        typical_days=typical_days,
    )
    session.add(destination)
    session.flush()

    if with_factors:
        session.add(
            DestinationFactor(
                destination_id=destination.id,
                environmental=environmental,
                community=70.0,
                crowd=60.0,
                infrastructure=50.0,
                suitability=40.0,
                source_ref="test fixture",
                confidence=confidence,
            )
        )
        session.flush()

    return destination


def test_returns_the_contract_shape(
    empty_destinations: Session, db_client: TestClient
) -> None:
    add_destination(empty_destinations, "Belihuloya")

    response = db_client.post("/api/recommend", json=REQUEST)
    assert response.status_code == 200

    body = response.json()
    RecommendEnvelope.model_validate(body)

    result = body["data"]["results"][0]
    assert result["name"] == "Belihuloya"
    assert set(result["factors"]) == {
        "environmental",
        "community",
        "crowd",
        "infrastructure",
        "suitability",
    }
    assert len(result["contributions"]) == 5
    assert all(c["type"] == "exact" for c in result["contributions"])
    # Percentages must add up, or the bars in F3 will not.
    assert sum(c["percent"] for c in result["contributions"]) == 100
    assert result["explanation"].startswith("Recommended mainly because of ")
    assert result["confidence"] == "measured"


def test_confidence_comes_from_destination_factors(
    empty_destinations: Session, db_client: TestClient
) -> None:
    add_destination(empty_destinations, "Meemure", confidence="estimated")

    body = db_client.post("/api/recommend", json=REQUEST).json()
    assert body["data"]["results"][0]["confidence"] == "estimated"


def test_over_budget_destination_is_excluded_not_scored_low(
    empty_destinations: Session, db_client: TestClient
) -> None:
    """features.md F2: budget is a filter, not a penalty."""
    add_destination(empty_destinations, "Affordable", cost_band="low")
    add_destination(empty_destinations, "Expensive", cost_band="high")

    body = db_client.post(
        "/api/recommend", json={**REQUEST, "budget_lkr": 50000}
    ).json()

    names = [row["name"] for row in body["data"]["results"]]
    assert names == ["Affordable"]
    # Not present at all, rather than present with a low score.
    assert "Expensive" not in names
    assert body["meta"]["excluded"]["over_budget"] == 1
    assert body["meta"]["excluded"]["total"] == 1


def test_trip_longer_than_duration_is_excluded(
    empty_destinations: Session, db_client: TestClient
) -> None:
    add_destination(empty_destinations, "Short", typical_days=2)
    add_destination(empty_destinations, "Long", typical_days=9)

    body = db_client.post("/api/recommend", json={**REQUEST, "duration_days": 4}).json()

    assert [row["name"] for row in body["data"]["results"]] == ["Short"]
    assert body["meta"]["excluded"]["over_duration"] == 1


def test_destination_without_factors_is_counted_not_dropped(
    empty_destinations: Session, db_client: TestClient
) -> None:
    add_destination(empty_destinations, "Scored")
    add_destination(empty_destinations, "NoFactors", with_factors=False)

    body = db_client.post("/api/recommend", json=REQUEST).json()

    assert [row["name"] for row in body["data"]["results"]] == ["Scored"]
    assert body["meta"]["excluded"]["missing_factors"] == 1


def test_every_destination_is_scored_or_excluded(
    empty_destinations: Session, db_client: TestClient
) -> None:
    """features.md F2: no silent drops. The two numbers must account for all."""
    add_destination(empty_destinations, "A", cost_band="low", typical_days=2)
    add_destination(empty_destinations, "B", cost_band="high", typical_days=2)
    add_destination(empty_destinations, "C", cost_band="low", typical_days=30)
    add_destination(empty_destinations, "D", with_factors=False)

    body = db_client.post("/api/recommend", json=REQUEST).json()

    scored = len(body["data"]["results"])
    excluded = body["meta"]["excluded"]["total"]
    assert scored + excluded == 4


def test_results_are_ranked_highest_score_first(
    empty_destinations: Session, db_client: TestClient
) -> None:
    add_destination(empty_destinations, "Low", environmental=10.0)
    add_destination(empty_destinations, "High", environmental=95.0)
    add_destination(empty_destinations, "Middle", environmental=50.0)

    body = db_client.post("/api/recommend", json=REQUEST).json()

    assert [row["name"] for row in body["data"]["results"]] == [
        "High",
        "Middle",
        "Low",
    ]
    scores = [row["sustainability_score"] for row in body["data"]["results"]]
    assert scores == sorted(scores, reverse=True)


def test_second_ranked_destination_gets_the_ranked_below_template(
    empty_destinations: Session, db_client: TestClient
) -> None:
    add_destination(empty_destinations, "Best", environmental=95.0)
    add_destination(empty_destinations, "Second", environmental=50.0)
    add_destination(empty_destinations, "Third", environmental=10.0)

    results = db_client.post("/api/recommend", json=REQUEST).json()["data"]["results"]

    assert [row["name"] for row in results] == ["Best", "Second", "Third"]
    assert results[0]["explanation"].startswith("Recommended mainly because of ")
    # Each lower result is explained against the one directly above it.
    assert results[1]["explanation"].startswith("Ranked below Best mainly because of ")
    assert results[2]["explanation"].startswith(
        "Ranked below Second mainly because of "
    )


def test_every_result_has_a_non_empty_explanation(
    empty_destinations: Session, db_client: TestClient
) -> None:
    """F3: no result is shown without a reason."""
    for number in range(5):
        add_destination(
            empty_destinations,
            f"Destination {number}",
            environmental=float(20 * number + 5),
        )

    results = db_client.post("/api/recommend", json=REQUEST).json()["data"]["results"]

    assert len(results) == 5
    for row in results:
        assert row["explanation"].endswith(".")
        assert len(row["explanation"]) > 20
        assert len(row["contributions"]) <= 5
        assert sum(c["percent"] for c in row["contributions"]) == 100


def test_explanations_are_repeatable(
    empty_destinations: Session, db_client: TestClient
) -> None:
    """Same request, same words. Nothing here is generated."""
    add_destination(empty_destinations, "Belihuloya")
    add_destination(empty_destinations, "Meemure", environmental=60.0)

    first = db_client.post("/api/recommend", json=REQUEST).json()["data"]
    second = db_client.post("/api/recommend", json=REQUEST).json()["data"]
    assert first == second


def test_twenty_destinations_score_in_under_two_seconds(
    empty_destinations: Session, db_client: TestClient
) -> None:
    """features.md F2 acceptance criterion."""
    for number in range(20):
        add_destination(empty_destinations, f"Destination {number:02d}")

    started = time.perf_counter()
    response = db_client.post("/api/recommend", json=REQUEST)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert len(response.json()["data"]["results"]) == 20
    assert elapsed < 2.0, f"took {elapsed:.3f}s"


def test_malformed_body_returns_422_not_500(client: TestClient) -> None:
    response = client.post("/api/recommend", json={"budget_lkr": "not a number"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_sustainability_weight_returns_422_not_500(
    db_client: TestClient,
) -> None:
    """A word the schema cannot check, only config/weights.yaml knows."""
    response = db_client.post(
        "/api/recommend", json={**REQUEST, "sustainability_weight": "extremely"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "sustainability_weight" in body["error"]["message"]
