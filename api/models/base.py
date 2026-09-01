"""Declarative base shared by every table.

Alembic autogenerate compares against Base.metadata, so every model module has
to be imported before it runs. api/models/__init__.py does that.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
