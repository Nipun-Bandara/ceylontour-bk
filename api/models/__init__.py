"""Importing every model here means Base.metadata is complete after a single
`from api.models import Base`, which is what Alembic needs.
"""

from api.models.base import Base
from api.models.destination import Destination, DestinationFactor
from api.models.index_weight import IndexWeight
from api.models.pressure import PressureForecast, RegionPressureHistory
from api.models.search_log import SearchLog
from api.models.user import User

__all__ = [
    "Base",
    "Destination",
    "DestinationFactor",
    "IndexWeight",
    "PressureForecast",
    "RegionPressureHistory",
    "SearchLog",
    "User",
]
