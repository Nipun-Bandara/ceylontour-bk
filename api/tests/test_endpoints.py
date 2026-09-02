"""One test per endpoint: 200, and a body that matches the contract.

model_validate does the shape checking. If a router ever returns a field the
schema does not declare, or drops one it does, these fail.

recommend, risk, alternatives, simulate and destinations are no longer here.
They read the database now, so their tests live in the per-endpoint modules
beside this one.

What is left is the endpoints still returning mocks: dashboard and auth.
"""

from fastapi.testclient import TestClient

from api.schemas.auth import LoginData
from api.schemas.common import Envelope
from api.schemas.dashboard import DashboardSummaryData

RECOMMEND_REQUEST = {
    "budget_lkr": 50000,
    "duration_days": 4,
    "interest": "nature",
    "crowd_preference": "low",
    "sustainability_weight": "high",
    "travel_month": 9,
}


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    Envelope[dict[str, str]].model_validate(body)
    assert body["data"]["status"] == "ok"
    # Every response carries the versions, including this one.
    assert body["meta"]["model_version"]
    assert body["meta"]["index_version"]


def test_dashboard_summary(client: TestClient) -> None:
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    Envelope[DashboardSummaryData].model_validate(response.json())


def test_auth_login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "officer@sltda.gov.lk", "password": "not-checked-yet"},
    )
    assert response.status_code == 200
    Envelope[LoginData].model_validate(response.json())


def test_bad_input_returns_error_shape_not_500(client: TestClient) -> None:
    """Hard rule 2: bad input never returns a 500."""
    response = client.post(
        "/api/recommend", json={**RECOMMEND_REQUEST, "travel_month": 99}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "travel_month" in error["message"]
