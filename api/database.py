"""Database engine and session factory.

Nothing in this branch queries the database yet; the routers return mocks. This
exists so the models and the Alembic migration have one place to get the
connection from.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import settings

# create_engine does not open a connection, so importing this module is safe
# even when Postgres is not running (the tests rely on that).
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
