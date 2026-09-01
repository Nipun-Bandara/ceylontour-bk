"""POST /api/auth/login. Mock data only.

No token is signed and no password is checked here. Real JWT issue and
password hashing land with the dashboard branch (features.md F8).
"""

from typing import Any

from fastapi import APIRouter

from api.envelope import envelope
from api.schemas.auth import LoginData, LoginRequest
from api.schemas.common import Envelope

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Envelope[LoginData])
def login(request: LoginRequest) -> dict[str, Any]:
    data = LoginData(
        # Not credentials, just mock strings until JWT issue is built.
        access_token="mock-token-not-a-real-jwt",  # noqa: S106
        token_type="bearer",  # noqa: S106
        role="authority",
    )
    return envelope(data)
