"""SQLAlchemy engine / session management.

The DATABASE_URL fully controls the backend, so the same code runs against the
PostgreSQL production/dev URL or a plain SQLite URL (used by the test suite).
"""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import Engine, create_engine, event, select, text
from sqlalchemy.exc import ProgrammingError
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


def _context_values(
    *,
    role: str = "",
    user_id: int | None = None,
    auth_user_id: UUID | None = None,
) -> dict[str, str]:
    return {
        "role": role,
        "user_id": str(user_id) if user_id is not None else "",
        "auth_user_id": str(auth_user_id) if auth_user_id else "",
    }


def _apply_transaction_context(connection, context: dict[str, str]) -> None:
    connection.execute(
        text(
            "SELECT set_config('hosteldesk.role', :role, true), "
            "set_config('hosteldesk.user_id', :user_id, true), "
            "set_config('hosteldesk.auth_user_id', :auth_user_id, true)"
        ),
        context,
    )


@event.listens_for(SessionLocal, "after_begin")
def _restore_transaction_security_context(session, transaction, connection) -> None:
    """Reapply RLS identity after every commit starts a fresh transaction."""
    if connection.dialect.name == "postgresql":
        _apply_transaction_context(
            connection,
            session.info.get("hosteldesk_security_context", _context_values()),
        )


def _set_security_context(
    db: Session,
    *,
    role: str = "",
    user_id: int | None = None,
    auth_user_id: UUID | None = None,
) -> None:
    """Set validated request identity for RLS policies on the API DB role."""
    if not settings.database_url.startswith("postgresql"):
        return
    context = _context_values(
        role=role,
        user_id=user_id,
        auth_user_id=auth_user_id,
    )
    db.info["hosteldesk_security_context"] = context
    if db.in_transaction():
        _apply_transaction_context(db.connection(), context)


def set_database_security_context(db: Session, role: str) -> None:
    """Set the trusted server context for internal background/maintenance work."""
    _set_security_context(db, role=role)


def set_onboarding_security_context(db: Session, auth_user_id: UUID) -> None:
    """Restrict role-profile inserts to a server-created Auth identity."""
    _set_security_context(db, role="ONBOARDING", auth_user_id=auth_user_id)


def clear_database_security_context(db: Session) -> None:
    """Clear identity state and roll back transaction-local settings."""
    try:
        db.info["hosteldesk_security_context"] = _context_values()
        if db.in_transaction() and settings.database_url.startswith("postgresql"):
            _apply_transaction_context(db.connection(), _context_values())
        db.rollback()
    except Exception:  # noqa: BLE001 - always close the session after a failed reset
        db.rollback()
    finally:
        db.info.pop("hosteldesk_security_context", None)


@contextmanager
def system_database_context(db: Session):
    """Scoped privileged context for trusted maintenance/seed operations."""
    set_database_security_context(db, "SYSTEM")
    try:
        yield db
    finally:
        clear_database_security_context(db)


def get_db(request: Request) -> Generator[Session, None, None]:
    """Resolve request identity and set row-security context on the API DB role."""
    db = SessionLocal()
    try:
        authorization = request.headers.get("authorization")
        request.state.supabase_auth_user = None
        request.state.current_user = None

        from app.db.models import User, UserRole

        if authorization:
            from app.core.security import get_supabase_auth_user, parse_bearer_token

            auth_user = get_supabase_auth_user(parse_bearer_token(authorization))
            request.state.supabase_auth_user = auth_user
            try:
                auth_user_id = UUID(str(auth_user.get("id")))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The Supabase account is invalid.") from exc
            _set_security_context(
                db, role="ONBOARDING", auth_user_id=auth_user_id,
            )
            try:
                user = db.execute(
                    select(User).where(User.auth_user_id == auth_user_id)
                ).scalar_one_or_none()
            except ProgrammingError as exc:
                original = getattr(exc, "orig", exc)
                if getattr(original, "pgcode", None) == "42703" and "auth_user_id" in str(original):
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "HostelDesk database migration 66ae9ccc1b8a is required before Warden sign-in. "
                        "Apply Alembic migrations with an owner-level database connection.",
                    ) from exc
                raise
            if user is None:
                # Self-healing: if Supabase Auth already has a trusted role, provision missing user row
                app_meta = auth_user.get("app_metadata") or {}
                user_meta = auth_user.get("user_metadata") or {}
                role_val = app_meta.get("role") or user_meta.get("role")
                if isinstance(role_val, str) and role_val.upper() in UserRole.__members__:
                    from app.db.models import Worker, WorkerType

                    target_role = UserRole(role_val.upper())
                    name = (
                        user_meta.get("name")
                        or auth_user.get("email", "").split("@")[0]
                        or target_role.value.capitalize()
                    )
                    user = User(auth_user_id=auth_user_id, name=name, role=target_role)
                    db.add(user)
                    try:
                        db.flush()
                        if target_role is UserRole.WORKER:
                            set_database_security_context(db, "SYSTEM")
                            worker_type_str = str(user_meta.get("worker_type", "CLEANER")).upper()
                            worker_type = (
                                WorkerType(worker_type_str)
                                if worker_type_str in WorkerType.__members__
                                else WorkerType.CLEANER
                            )
                            db.add(Worker(user_id=user.id, worker_type=worker_type))
                        db.commit()
                        db.refresh(user)
                    except Exception:
                        db.rollback()
                        user = None

            if user is not None:
                _set_security_context(
                    db, role=user.role.value, user_id=user.id, auth_user_id=auth_user_id,
                )
            else:
                _set_security_context(
                    db, role="ONBOARDING", auth_user_id=auth_user_id,
                )
            request.state.current_user = user
        yield db
    finally:
        clear_database_security_context(db)
        db.close()
