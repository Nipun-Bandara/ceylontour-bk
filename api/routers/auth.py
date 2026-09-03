"""POST /api/auth/login.

Real authentication. Passwords are checked against an argon2 hash and a
successful login returns a short-lived JWT carrying the account's role.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.envelope import envelope
from api.schemas.auth import LoginData, LoginRequest
from api.schemas.common import Envelope
from api.services.security import authenticate, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for both "no such email" and "wrong password". Saying which one
# was wrong tells an attacker whether an account exists, and authenticate()
# already makes the two take the same time.
INVALID_CREDENTIALS = "Incorrect email or password"


@router.post("/login", response_model=Envelope[LoginData])
def login(
    request: LoginRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    user = authenticate(db, request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # LoginData has no password field, so the hash cannot leave here even by
    # accident: response_model drops anything not declared.
    data = LoginData(
        access_token=create_access_token(user),
        token_type="bearer",  # noqa: S106
        role=user.role,
    )
    return envelope(data)
