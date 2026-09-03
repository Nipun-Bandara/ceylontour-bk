"""Login, tokens and roles.

The dashboard is the only thing behind auth, so these check the door itself:
who gets in, who does not, and what leaks in the process.
"""

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.config import Settings, settings
from api.models import User
from api.schemas.auth import LoginData
from api.schemas.common import Envelope
from api.services.security import (
    AUTHORITY_ROLE,
    TOURIST_ROLE,
    create_access_token,
    hash_password,
    verify_password,
)

PASSWORD = "correct-horse-battery"  # noqa: S105
OTHER_PASSWORD = "wrong-horse-battery"  # noqa: S105


@pytest.fixture
def authority(db_session: Session) -> User:
    db_session.query(User).delete()
    user = User(
        email="officer@sltda.gov.lk",
        password_hash=hash_password(PASSWORD),
        role=AUTHORITY_ROLE,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def tourist(db_session: Session) -> User:
    user = User(
        email="tourist@example.com",
        password_hash=hash_password(PASSWORD),
        role=TOURIST_ROLE,
    )
    db_session.add(user)
    db_session.flush()
    return user


def login(client: TestClient, email: str, password: str):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


def test_login_succeeds_with_the_right_password(
    authority: User, db_client: TestClient
) -> None:
    response = login(db_client, authority.email, PASSWORD)
    assert response.status_code == 200

    body = response.json()
    Envelope[LoginData].model_validate(body)

    data = body["data"]
    assert data["token_type"] == "bearer"  # noqa: S105
    assert data["role"] == AUTHORITY_ROLE
    assert data["access_token"]


def test_token_carries_sub_and_role(
    authority: User, db_client: TestClient
) -> None:
    token = login(db_client, authority.email, PASSWORD).json()["data"][
        "access_token"
    ]
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )

    assert payload["sub"] == str(authority.id)
    assert payload["role"] == AUTHORITY_ROLE
    # Expiry is set and is not far away.
    expires = datetime.fromtimestamp(payload["exp"], tz=UTC)
    assert expires <= datetime.now(UTC) + timedelta(
        minutes=settings.jwt_expire_minutes + 1
    )
    assert expires > datetime.now(UTC)


def test_shipped_expiry_default_is_thirty_minutes() -> None:
    """features.md F8 asks for a short-lived token.

    Checks the default the repo ships, not the resolved setting: a deployment
    is free to set JWT_EXPIRE_MINUTES to something else, and that should not
    fail the suite.
    """
    assert Settings.model_fields["jwt_expire_minutes"].default == 30


def test_wrong_password_returns_401_with_the_error_shape(
    authority: User, db_client: TestClient
) -> None:
    response = login(db_client, authority.email, OTHER_PASSWORD)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "401"


def test_unknown_email_and_wrong_password_are_indistinguishable(
    authority: User, db_client: TestClient
) -> None:
    """Different messages would say whether an account exists."""
    missing = login(db_client, "nobody@example.com", PASSWORD)
    wrong = login(db_client, authority.email, OTHER_PASSWORD)

    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


def test_unknown_email_takes_comparable_time_to_a_wrong_password(
    authority: User, db_client: TestClient
) -> None:
    """A fast "no such user" is an account enumeration oracle.

    Both paths run one argon2 verify, so the times sit in the same range. The
    bound is loose on purpose; this catches "we skipped hashing entirely", not
    microseconds.
    """

    def average(email: str) -> float:
        samples = []
        for _ in range(3):
            started = time.perf_counter()
            login(db_client, email, OTHER_PASSWORD)
            samples.append(time.perf_counter() - started)
        return sum(samples) / len(samples)

    missing = average("nobody@example.com")
    existing = average(authority.email)

    slower, faster = max(missing, existing), min(missing, existing)
    assert slower < faster * 5, f"missing={missing:.4f}s existing={existing:.4f}s"


def test_password_hash_never_appears_in_any_response(
    authority: User, db_client: TestClient
) -> None:
    response = login(db_client, authority.email, PASSWORD)
    text = response.text

    assert authority.password_hash not in text
    assert PASSWORD not in text
    # argon2 hashes all start this way; none of it should be on the wire.
    assert "$argon2" not in text
    assert "password" not in text.lower()


def test_password_is_stored_only_as_a_hash(authority: User) -> None:
    assert authority.password_hash != PASSWORD
    assert authority.password_hash.startswith("$argon2")
    assert verify_password(PASSWORD, authority.password_hash)
    assert not verify_password(OTHER_PASSWORD, authority.password_hash)


def test_the_same_password_hashes_differently_each_time() -> None:
    """Salted, so two accounts with one password do not look alike."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_malformed_email_returns_422(db_client: TestClient) -> None:
    response = login(db_client, "not-an-email", PASSWORD)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_token_for_a_deleted_account_is_rejected(
    authority: User, db_session: Session, db_client: TestClient
) -> None:
    token = create_access_token(authority)
    db_session.delete(authority)
    db_session.flush()

    response = db_client.get(
        "/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_expired_token_is_rejected(
    authority: User, db_client: TestClient
) -> None:
    expired = jwt.encode(
        {
            "sub": str(authority.id),
            "role": AUTHORITY_ROLE,
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = db_client.get(
        "/api/dashboard/summary", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


def test_token_signed_with_another_secret_is_rejected(
    authority: User, db_client: TestClient
) -> None:
    forged = jwt.encode(
        {
            "sub": str(authority.id),
            "role": AUTHORITY_ROLE,
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        "not-the-real-secret",
        algorithm=settings.jwt_algorithm,
    )
    response = db_client.get(
        "/api/dashboard/summary", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401
