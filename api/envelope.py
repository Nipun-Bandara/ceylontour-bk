"""The response envelope every endpoint returns.

One helper so no route can forget the meta block, and so the versions are read
in exactly one place.
"""

from typing import Any

from api.config import settings
from api.schemas.common import Meta
from api.services.index import index_version


def meta_fields() -> dict[str, str]:
    """The meta values every response carries.

    index_version is read from config/weights.yaml rather than from settings,
    because it has to name the weights that actually produced the score. If it
    came from the environment it could drift from the file and quietly claim a
    score was reproducible when it was not.
    """
    return {
        "model_version": settings.model_version,
        "index_version": index_version(),
    }


def envelope(data: Any, meta: Meta | None = None) -> dict[str, Any]:
    """Wrap a payload as {"data": ..., "meta": {...}}.

    Pass meta to use a richer subclass, as /api/recommend does to report what
    it filtered out.
    """
    return {
        "data": data,
        "meta": meta if meta is not None else Meta(**meta_fields()),
    }
