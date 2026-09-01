"""Shared test fixtures.

Most tests need no database: the routers other than /api/recommend return
mocks, and the index is pure arithmetic. The recommend tests do need Postgres,
so they use db_client, which runs each test inside a transaction that is
rolled back afterwards. Nothing a test inserts survives it.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.database import engine, get_db
from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A session inside a transaction that is always rolled back.

    Skips rather than fails when Postgres is not running, so `pytest` still
    works on a laptop with nothing started. Those tests are not optional
    though: run them with `docker compose exec api pytest` before merging.
    """
    try:
        connection = engine.connect()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"Postgres is not reachable, run inside docker compose: {exc}")

    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_client(db_session: Session) -> Iterator[TestClient]:
    """A client whose requests run against db_session's transaction."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def empty_destinations(db_session: Session) -> Session:
    """Remove any seeded rows so a test controls the whole dataset.

    Safe because the surrounding transaction is rolled back.
    """
    db_session.execute(text("DELETE FROM destination_factors"))
    db_session.execute(text("DELETE FROM destinations"))
    db_session.flush()
    return db_session
