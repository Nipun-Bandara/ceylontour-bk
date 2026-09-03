"""Per-client rate limiting.

Lives in its own module so routers and main.py can both reach the limiter
without importing each other.

Limits are read through a callable rather than baked in at import time, so
changing the setting changes the limit without restarting the process. That is
what lets the tests exercise the real path at a low limit instead of mocking
it away.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from api.config import settings

limiter = Limiter(key_func=get_remote_address)


def recommend_limit() -> str:
    return settings.rate_limit_recommend


def risk_limit() -> str:
    return settings.rate_limit_risk


def reset() -> None:
    """Forget every counter. Used between tests."""
    limiter.reset()
