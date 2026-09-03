"""GET /api/dashboard/summary.

Behind auth, so most of these carry a token. The counts have to agree with the
destinations table exactly, and the recommended action has to come from the
data rather than from a string someone wrote in advance.
"""

from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.models import Destination, DestinationFactor, User
from api.routers.dashboard import ACTION_TEMPLATES, recommended_action
from api.schemas.common import Envelope
from api.schemas.dashboard import DashboardSummaryData
from api.services.security import AUTHORITY_ROLE, TOURIST_ROLE, create_access_token

PASSWORD = "correct-horse-battery"  # noqa: S105

# One per region the synthetic history covers, so every one can be banded.
SEEDED = [
    ("Belihuloya", "Sabaragamuwa"),
    ("Meemure", "Central"),
    ("Ella", "Uva"),
    ("Riverston", "Central"),
]

FACTORS = {
    "environmental": 90.0,
    "community": 85.0,
    "crowd": 80.0,
    "infrastructure": 70.0,
    "suitability": 75.0,
}


def make_user(session: Session, email: str, role: str) -> User:
    from api.services.security import hash_password

    user = User(email=email, password_hash=hash_password(PASSWORD), role=role)
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def authority_headers(db_session: Session) -> dict[str, str]:
    db_session.query(User).delete()
    user = make_user(db_session, "officer@sltda.gov.lk", AUTHORITY_ROLE)
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def tourist_headers(db_session: Session) -> dict[str, str]:
    user = make_user(db_session, "tourist@example.com", TOURIST_ROLE)
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def seeded(forecast_ready: Session, empty_destinations: Session) -> int:
    for index, (name, region) in enumerate(SEEDED):
        destination = Destination(
            name=name,
            lat=6.7 + index * 0.2,
            lon=80.7 + index * 0.1,
            district="Ratnapura",
            region=region,
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
                **FACTORS,
                source_ref="test fixture",
                confidence="measured",
            )
        )
        empty_destinations.flush()
    return len(SEEDED)


def test_no_token_returns_401(seeded: int, db_client: TestClient) -> None:
    response = db_client.get("/api/dashboard/summary")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "401"


def test_tourist_role_returns_403_not_401_and_not_blank(
    seeded: int, tourist_headers: dict[str, str], db_client: TestClient
) -> None:
    """features.md F8: tourist-role users get 403, not a blank page."""
    response = db_client.get("/api/dashboard/summary", headers=tourist_headers)

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "403"
    # Not blank: it says why.
    assert body["error"]["message"]
    assert "authority" in body["error"]["message"].lower()


def test_authority_role_gets_in(
    seeded: int, authority_headers: dict[str, str], db_client: TestClient
) -> None:
    response = db_client.get("/api/dashboard/summary", headers=authority_headers)
    assert response.status_code == 200
    Envelope[DashboardSummaryData].model_validate(response.json())


def test_band_counts_equal_the_destinations_table_count(
    seeded: int,
    db_session: Session,
    authority_headers: dict[str, str],
    db_client: TestClient,
) -> None:
    data = db_client.get(
        "/api/dashboard/summary", headers=authority_headers
    ).json()["data"]

    table_count = db_session.query(Destination).count()
    assert data["destinations_monitored"] == table_count == seeded

    counts = data["band_counts"]
    assert counts["low"] + counts["medium"] + counts["high"] == table_count


def test_highest_pressure_is_capped_at_five_and_sorted(
    seeded: int, authority_headers: dict[str, str], db_client: TestClient
) -> None:
    data = db_client.get(
        "/api/dashboard/summary", headers=authority_headers
    ).json()["data"]

    listed = data["highest_pressure"]
    assert len(listed) <= 5
    pressures = [row["predicted_pressure"] for row in listed]
    assert pressures == sorted(pressures, reverse=True)


def test_global_feature_importance_is_present_and_normalised(
    seeded: int, authority_headers: dict[str, str], db_client: TestClient
) -> None:
    data = db_client.get(
        "/api/dashboard/summary", headers=authority_headers
    ).json()["data"]

    importance = data["global_feature_importance"]
    assert importance
    assert sum(row["importance"] for row in importance) == pytest.approx(
        1.0, abs=0.01
    )
    # Plain language, not column names.
    assert all("_" not in row["feature"] for row in importance)
    # Largest first.
    values = [row["importance"] for row in importance]
    assert values == sorted(values, reverse=True)


def test_recommended_action_mentions_a_real_region(
    seeded: int, authority_headers: dict[str, str], db_client: TestClient
) -> None:
    data = db_client.get(
        "/api/dashboard/summary", headers=authority_headers
    ).json()["data"]

    action = data["recommended_action"]
    assert action.endswith(".")
    regions = {region for _, region in SEEDED}
    # Either it names one of the real regions, or everything is quiet.
    assert any(region in action for region in regions) or "low pressure" in action


def test_no_password_hash_in_the_dashboard_response(
    seeded: int, authority_headers: dict[str, str], db_client: TestClient
) -> None:
    text = db_client.get(
        "/api/dashboard/summary", headers=authority_headers
    ).text
    assert "$argon2" not in text
    assert "password" not in text.lower()


def test_action_template_for_one_high_pressure_destination() -> None:
    action = recommended_action(
        Counter({"high": 1, "low": 2}), {"high": Counter({"Uva": 1}), "low": Counter()}
    )
    assert action == ACTION_TEMPLATES["high_one"].format(count=1, region="Uva")


def test_action_template_for_several_high_pressure_destinations() -> None:
    action = recommended_action(
        Counter({"high": 3}),
        {"high": Counter({"Uva": 2, "Central": 1}), "low": Counter()},
    )
    assert "3 destinations are at high pressure" in action
    # Names the region carrying the most of them.
    assert "Uva" in action


def test_action_falls_back_to_medium_then_to_all_low() -> None:
    medium = recommended_action(
        Counter({"medium": 2, "low": 1}),
        {"high": Counter(), "medium": Counter({"Central": 2}), "low": Counter()},
    )
    assert "No destination is at high pressure" in medium
    assert "Central" in medium

    quiet = recommended_action(
        Counter({"low": 4}),
        {"high": Counter(), "medium": Counter(), "low": Counter({"Uva": 4})},
    )
    assert quiet == ACTION_TEMPLATES["all_low"].format(count=4)


def test_action_with_no_destinations() -> None:
    assert recommended_action(
        Counter(), {"high": Counter(), "medium": Counter(), "low": Counter()}
    ) == ACTION_TEMPLATES["none"]


def test_action_is_repeatable_on_a_tie() -> None:
    """Two regions with equal counts must not reshuffle between refreshes."""
    counts = Counter({"high": 2})
    regions = {"high": Counter({"Uva": 1, "Central": 1}), "low": Counter()}
    first = recommended_action(counts, regions)
    for _ in range(5):
        assert recommended_action(counts, regions) == first
    # Alphabetical on a tie.
    assert "Central" in first
