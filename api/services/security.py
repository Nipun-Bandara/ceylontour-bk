"""Password hashing, JWTs, and who is calling.

Passwords are hashed with argon2 and never stored or returned as text
(features.md F8). Tokens are short-lived and signed with a secret from the
environment.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import settings
from api.database import get_db
from api.models import User

AUTHORITY_ROLE = "authority"
TOURIST_ROLE = "tourist"

_context = CryptContext(schemes=["argon2"], deprecated="auto")

# auto_error=False so a missing header reaches our own code. HTTPBearer's
# default is to raise 403 when no credentials are sent, and F8 wants 401 for
# "you did not say who you are" and 403 only for "you are not allowed".
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return bool(_context.verify(password, password_hash))


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real argon2 hash of a throwaway value.

    Used to burn the same CPU time when the email does not exist. Without it,
    a missing account answers noticeably faster than a wrong password, and
    that difference is enough to enumerate who has an account.
    """
    return hash_password("not-a-real-password-only-for-timing")


def authenticate(db: Session, email: str, password: str) -> User | None:
    """The user, or None. Takes the same time either way."""
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is None:
        # Verify against the dummy so the work done matches the found case,
        # then fail regardless.
        verify_password(password, _dummy_hash())
        return None

    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(user: User) -> str:
    """A signed JWT carrying who they are and what they may do."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _unauthorised(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The user behind the bearer token, or 401."""
    if credentials is None:
        raise _unauthorised("Not authenticated")

    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorised("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorised("Invalid token") from exc

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorised("Invalid token")

    user = db.get(User, int(subject))
    if user is None:
        # The token is valid but the account is gone.
        raise _unauthorised("Invalid token")
    return user


def require_authority(user: User = Depends(get_current_user)) -> User:
    """403 for a signed-in user without the authority role.

    F8 is explicit: a tourist-role user gets a 403, not a blank page and not a
    401. They are authenticated fine; they are simply not allowed in.
    """
    if user.role != AUTHORITY_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account does not have access to the authority dashboard",
        )
    return user
