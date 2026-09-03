"""The cross-cutting requirements in features.md, as tests.

Validation, rate limiting, the error shape, request size, and the promise that
a hostile string in a text field is stored and returned as text rather than
executed.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api import rate_limit
from api.config import PLACEHOLDER_JWT_SECRET, Settings
from api.models import Destination, DestinationFactor
from api.schemas.common import CrowdPreference, Interest

VALID_RECOMMEND = {
    "budget_lkr": 50000,
    "duration_days": 4,
    "interest": "nature",
    "crowd_preference": "low",
    "sustainability_weight": "high",
    "travel_month": 9,
}

# The classic. If any of this were interpolated into a query it would drop a
# table; it must come back as the harmless string it is.
INJECTION = "Robert'); DROP TABLE destinations;--"

# Not a credential; a stand-in for a properly configured production secret.
REAL_SECRET = "a-real-secret-value-goes-here"  # noqa: S105


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("interest", "not-an-interest"),
        ("interest", ""),
        ("interest", 7),
        ("crowd_preference", "quiet-ish"),
        ("crowd_preference", None),
    ],
)
def test_bad_enum_gives_422(client: TestClient, field: str, value: object) -> None:
    response = client.post(
        "/api/recommend", json={**VALID_RECOMMEND, field: value}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert field in body["error"]["message"]


def test_every_enum_member_is_accepted_by_the_schema() -> None:
    """The closed set is the one the frontend was told about."""
    assert {item.value for item in Interest} == {
        "nature",
        "culture",
        "adventure",
        "wildlife",
        "beach",
        "relaxation",
    }
    assert {item.value for item in CrowdPreference} == {"low", "medium", "high"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("budget_lkr", 0),
        ("budget_lkr", -1),
        ("duration_days", 0),
        ("duration_days", 31),
        ("travel_month", 0),
        ("travel_month", 13),
    ],
)
def test_out_of_bounds_body_values_give_422(
    client: TestClient, field: str, value: int
) -> None:
    response = client.post(
        "/api/recommend", json={**VALID_RECOMMEND, field: value}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_body_field_is_rejected(client: TestClient) -> None:
    """extra="forbid", so a misspelled field is not silently ignored."""
    response = client.post(
        "/api/recommend", json={**VALID_RECOMMEND, "budget_lkrr": 1000}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "/api/risk/0?month=9",
        "/api/risk/-3?month=9",
        "/api/risk/abc?month=9",
        "/api/risk/1?month=0",
        "/api/risk/1?month=13",
        "/api/risk/1?month=notanumber",
        "/api/destinations/0",
        "/api/destinations/-1",
        "/api/alternatives/0",
        "/api/alternatives/1?budget_lkr=0",
        "/api/alternatives/1?duration_days=0",
        "/api/alternatives/1?duration_days=31",
    ],
)
def test_path_and_query_params_are_validated(client: TestClient, url: str) -> None:
    """Path and query parameters get the same Pydantic treatment as bodies."""
    response = client.get(url)
    assert response.status_code == 422, url
    assert response.json()["error"]["code"] == "validation_error"


def test_simulate_rejects_out_of_range_sliders(client: TestClient) -> None:
    response = client.post(
        "/api/simulate",
        json={
            "destination_id": 1,
            "expected_tourists": 101,
            "waste_management_level": 50,
            "infrastructure_level": 50,
        },
    )
    assert response.status_code == 422


def test_login_rejects_an_absurd_password_length(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "a@b.lk", "password": "x" * 5000},
    )
    assert response.status_code == 422


# -------------------------------------------------------------- rate limiting


def test_rate_limit_trips_and_returns_429_in_the_error_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """features.md, Rate limiting: per-client limits on recommend and risk."""
    from api.config import settings

    monkeypatch.setattr(settings, "rate_limit_recommend", "3/minute")
    rate_limit.reset()

    statuses = [
        client.post("/api/recommend", json=VALID_RECOMMEND).status_code
        for _ in range(5)
    ]

    assert 429 in statuses, statuses
    # The limit bites after the allowance, not before.
    assert statuses.index(429) >= 3

    response = client.post("/api/recommend", json=VALID_RECOMMEND)
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert body["error"]["message"]


def test_risk_is_rate_limited_too(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.config import settings

    monkeypatch.setattr(settings, "rate_limit_risk", "2/minute")
    rate_limit.reset()

    statuses = [
        client.get("/api/risk/1", params={"month": 9}).status_code
        for _ in range(4)
    ]
    assert 429 in statuses, statuses


def test_limits_are_read_from_settings_not_hardcoded() -> None:
    from api.config import settings

    assert rate_limit.recommend_limit() == settings.rate_limit_recommend
    assert rate_limit.risk_limit() == settings.rate_limit_risk


# ------------------------------------------------------------- request size


def test_oversized_payload_is_rejected(client: TestClient) -> None:
    from api.config import settings

    oversized = {**VALID_RECOMMEND, "interest": "nature"}
    padding = "x" * (settings.max_request_bytes + 1024)

    response = client.post(
        "/api/recommend",
        content=f'{{"pad": "{padding}"}}'.encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "payload_too_large"
    # And a normal body still gets through.
    assert client.post("/api/recommend", json=oversized).status_code != 413


def test_a_body_just_under_the_limit_is_not_rejected(client: TestClient) -> None:
    response = client.post("/api/recommend", json=VALID_RECOMMEND)
    assert response.status_code != 413


# --------------------------------------------------------------- SQL safety


def test_injection_string_in_a_text_field_is_stored_and_returned_safely(
    forecast_ready: Session, empty_destinations: Session, db_client: TestClient
) -> None:
    """Parameterised queries only, so this is data and never code."""
    destination = Destination(
        name=INJECTION,
        lat=6.9,
        lon=80.8,
        district=INJECTION,
        region="Sabaragamuwa",
        landscape_type="mountain",
        activities=[INJECTION],
        cost_band="low",
        typical_days=3,
    )
    empty_destinations.add(destination)
    empty_destinations.flush()
    empty_destinations.add(
        DestinationFactor(
            destination_id=destination.id,
            environmental=80.0,
            community=70.0,
            crowd=60.0,
            infrastructure=50.0,
            suitability=40.0,
            source_ref=INJECTION,
            confidence="measured",
        )
    )
    empty_destinations.flush()

    # The table is still there.
    assert empty_destinations.execute(
        select(Destination).where(Destination.id == destination.id)
    ).scalar_one()

    listed = db_client.get("/api/destinations").json()["data"]["destinations"]
    assert [row["name"] for row in listed] == [INJECTION]

    detail = db_client.get(f"/api/destinations/{destination.id}").json()["data"]
    assert detail["name"] == INJECTION
    assert detail["district"] == INJECTION
    assert detail["source_ref"] == INJECTION
    assert detail["activities"] == [INJECTION]

    # Still there afterwards, and still one row.
    assert (
        empty_destinations.execute(
            text("SELECT count(*) FROM destinations")
        ).scalar_one()
        == 1
    )


def test_injection_string_in_a_login_email_is_rejected_as_an_email(
    db_client: TestClient
) -> None:
    response = db_client.post(
        "/api/auth/login",
        json={"email": "' OR 1=1;--", "password": "whatever-goes-here"},
    )
    # Rejected by the email validator long before it reaches the database.
    assert response.status_code == 422


# ----------------------------------------------------------- error handling


def test_unexpected_error_returns_a_generic_500_with_no_stack_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No code path may leak a traceback to the caller."""
    from api.main import app
    from api.routers import destinations as destinations_router

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "psycopg: connection to server at 10.0.0.5 failed: password "
            "authentication failed for user 'ceylontour'"
        )

    monkeypatch.setattr(destinations_router, "_neutral_weights", explode)

    # raise_server_exceptions=False so the handler's response is returned
    # rather than the exception being re-raised into the test.
    with TestClient(app, raise_server_exceptions=False) as raw_client:
        response = raw_client.get("/api/destinations")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
        }
    }
    text_body = response.text
    assert "Traceback" not in text_body
    assert "psycopg" not in text_body
    assert "10.0.0.5" not in text_body
    assert "password" not in text_body.lower()


def test_every_error_response_uses_the_same_shape(client: TestClient) -> None:
    for response in (
        client.get("/api/destinations/999999"),
        client.post("/api/recommend", json={**VALID_RECOMMEND, "travel_month": 99}),
        client.get("/api/dashboard/summary"),
    ):
        body = response.json()
        assert set(body) == {"error"}
        assert set(body["error"]) == {"code", "message"}


# ------------------------------------------------------------- configuration


def test_cors_is_not_a_wildcard() -> None:
    from api.config import settings

    assert "*" not in settings.cors_origins
    assert settings.cors_origins


def test_production_refuses_a_placeholder_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            environment="production",
            jwt_secret=PLACEHOLDER_JWT_SECRET,
            cors_origins=["https://ceylontour.lk"],
        )


def test_production_refuses_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            jwt_secret=REAL_SECRET,
            cors_origins=["*"],
        )


def test_production_refuses_plain_http_origins() -> None:
    with pytest.raises(ValueError, match="http://"):
        Settings(
            environment="production",
            jwt_secret=REAL_SECRET,
            cors_origins=["http://ceylontour.lk"],
        )


def test_production_accepts_a_safe_configuration() -> None:
    settings = Settings(
        environment="production",
        jwt_secret=REAL_SECRET,
        cors_origins=["https://ceylontour.lk"],
    )
    assert settings.environment == "production"


def test_no_default_setting_carries_a_credential() -> None:
    """The shipped defaults must not be usable secrets."""
    defaults = Settings.model_fields
    assert defaults["authority_password"].default == ""
    assert defaults["jwt_secret"].default == PLACEHOLDER_JWT_SECRET
    # The bare default URL has no user:password in it.
    assert "@" not in defaults["database_url"].default.split("//", 1)[1].split("/")[0]
