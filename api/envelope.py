"""The response envelope every endpoint returns.

One helper so no route can forget the meta block, and so the versions are read
from settings in exactly one place.
"""

from typing import Any

from api.config import settings
from api.schemas.common import Meta


def envelope(data: Any) -> dict[str, Any]:
    """Wrap a payload as {"data": ..., "meta": {...}}."""
    return {
        "data": data,
        "meta": Meta(
            model_version=settings.model_version,
            index_version=settings.index_version,
        ),
    }
