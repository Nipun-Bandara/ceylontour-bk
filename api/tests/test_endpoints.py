"""One test per endpoint: 200, and a body that matches the contract.

model_validate does the shape checking. If a router ever returns a field the
schema does not declare, or drops one it does, these fail.

/api/recommend is no longer here. It reads the database now, so its tests live
in test_recommend_endpoint.py.
"""

from fastapi.testclient import TestClient

from api.schemas.alternatives import AlternativesData
from api.schemas.auth import LoginData
from api.schemas.common import Envelope
from api.schemas.dashboard import DashboardSummaryData
from api.schemas.destinations import DestinationDetail, DestinationListData
from api.schemas.risk import RiskData
from api.schemas.simulate import SimulateData

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


def test_list_destinations(client: TestClient) -> None:
    response = client.get("/api/destinations")
    assert response.status_code == 200
    Envelope[DestinationListData].model_validate(response.json())


def test_get_destination(client: TestClient) -> None:
    response = client.get("/api/destinations/7")
    assert response.status_code == 200
    body = response.json()
    Envelope[DestinationDetail].model_validate(body)
    assert body["data"]["id"] == 7


def test_get_risk(client: TestClient) -> None:
    response = client.get("/api/risk/7", params={"month": 9})
    assert response.status_code == 200
    body = response.json()
    Envelope[RiskData].model_validate(body)
    # SHAP values are estimates and must be labelled as such.
    assert all(c["type"] == "estimated" for c in body["data"]["contributions"])
    assert body["data"]["scope"] == "regional"


def test_get_alternatives(client: TestClient) -> None:
    response = client.get("/api/alternatives/3")
    assert response.status_code == 200
    body = response.json()
    Envelope[AlternativesData].model_validate(body)
    assert len(body["data"]["alternatives"]) == 3


def test_simulate(client: TestClient) -> None:
    response = client.post(
        "/api/simulate",
        json={
            "destination_id": 7,
            "expected_tourists": 1200,
            "waste_management_level": 40,
            "infrastructure_level": 55,
        },
    )
    assert response.status_code == 200
    Envelope[SimulateData].model_validate(response.json())


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
