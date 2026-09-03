"""POST /api/auth/login — JWT issue for authority users."""

from pydantic import BaseModel, EmailStr, Field

# argon2 handles long inputs fine, but there is no reason to hash a megabyte.
MAX_PASSWORD_LENGTH = 256


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class LoginData(BaseModel):
    access_token: str
    token_type: str
    role: str
