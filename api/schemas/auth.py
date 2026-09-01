"""POST /api/auth/login — JWT issue for authority users."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginData(BaseModel):
    access_token: str
    token_type: str
    role: str
