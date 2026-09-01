"""Shared test fixtures.

Nothing here touches Postgres. The routers return mocks, so the tests run
without docker-compose up.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
