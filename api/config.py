"""Application settings, read from the environment.

Nothing is hardcoded here that differs between a laptop and the demo machine,
so the same image runs in both places (features.md, Secrets).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # protected_namespaces is cleared because pydantic reserves the "model_"
    # prefix by default and the API contract requires a field called
    # model_version.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    environment: str = "development"

    # "db" and "cache" are the docker-compose service names.
    database_url: str = "postgresql+psycopg://ceylontour:ceylontour@db:5432/ceylontour"
    redis_url: str = "redis://cache:6379/0"

    # Returned in the meta block of every response so any explanation shown to
    # a user can be reproduced later (features.md, Traceability).
    model_version: str = "pressure-v1.2"
    index_version: str = "weights-v1"

    cors_origins: list[str] = ["http://localhost:3000"]

    # A placeholder the environment overrides, not a real secret.
    # Deployment must set JWT_SECRET.
    jwt_secret: str = "change-me"  # noqa: S105
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


settings = Settings()
