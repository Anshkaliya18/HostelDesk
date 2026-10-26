"""SQLAlchemy engine / session management.

The DATABASE_URL fully controls the backend, so the same code runs against the
PostgreSQL production/dev URL or a plain SQLite URL (used by the test suite).
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


@lru_cache
def get_engine() -> Engine:
    url = settings.database_url
    engine_kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:", "sqlite://:memory:"):
            # Single shared in-memory connection for the FastAPI TestClient.
            from sqlalchemy.pool import StaticPool

            engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **engine_kwargs)
    if url.startswith("sqlite"):
        # SQLite only enforces foreign keys when the pragma is enabled per
        # connection; our models rely on FK integrity.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


SessionLocal = sessionmaker(
    bind=get_engine(),
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that always yields a clean session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
