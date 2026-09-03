"""Application settings, read from the environment.

Nothing is hardcoded here that differs between a laptop and the demo machine,
so the same image runs in both places (features.md, Secrets).

No default in this file is a real credential. The database URL carries no
username or password, and the JWT secret is an obvious placeholder that
production refuses to start with.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_JWT_SECRET = "change-me"  # noqa: S105
PRODUCTION = "production"


class Settings(BaseSettings):
    # protected_namespaces is cleared because pydantic reserves the "model_"
    # prefix by default and the contract requires a field called
    # model_version.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    environment: str = "development"

    # "db" and "cache" are the docker-compose service names. No credentials
    # here: DATABASE_URL in the environment carries them, and this bare
    # default fails to connect rather than quietly using a known password.
    database_url: str = "postgresql+psycopg://db:5432/ceylontour"
    redis_url: str = "redis://cache:6379/0"

    # Returned in the meta block of every response so any explanation shown to
    # a user can be reproduced later (features.md, Traceability).
    model_version: str = "pressure-v1.2"
    index_version: str = "weights-v1"

    # The deployed frontend origin. Never "*": with allow_credentials on, a
    # wildcard would let any site read an authenticated response.
    cors_origins: list[str] = ["http://localhost:3000"]

    # A placeholder the environment overrides, not a real secret.
    # Deployment must set JWT_SECRET.
    jwt_secret: str = PLACEHOLDER_JWT_SECRET
    jwt_algorithm: str = "HS256"
    # Short on purpose. A dashboard token that lives for hours is a token
    # someone leaves open on a demo laptop (features.md F8).
    jwt_expire_minutes: int = 30

    # The single authority account, created by `python -m api.seed_user`.
    # The password is never stored; only its argon2 hash reaches the database.
    authority_email: str = "authority@ceylontour.lk"
    authority_password: str = ""  # noqa: S105

    # Per-client rate limits, in slowapi's "<count>/<period>" form
    # (features.md, Rate limiting). Generous enough that a real user browsing
    # never notices, low enough that a script does.
    rate_limit_recommend: str = "60/minute"
    rate_limit_risk: str = "120/minute"

    # Largest request body accepted, in bytes. Every endpoint here takes a
    # small JSON object, so anything larger is a mistake or an attack.
    max_request_bytes: int = 64 * 1024

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> "Settings":
        """Fail loudly at startup rather than run insecurely in production."""
        if self.environment.lower() != PRODUCTION:
            return self

        problems = []
        if self.jwt_secret == PLACEHOLDER_JWT_SECRET:
            problems.append("JWT_SECRET is still the placeholder")
        if "*" in self.cors_origins:
            problems.append('CORS_ORIGINS contains "*"')
        if any(origin.startswith("http://") for origin in self.cors_origins):
            problems.append("CORS_ORIGINS contains a plain http:// origin")

        if problems:
            raise ValueError(
                "Refusing to start in production: " + "; ".join(problems)
            )
        return self


settings = Settings()
