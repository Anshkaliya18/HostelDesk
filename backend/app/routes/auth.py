"""Supabase account creation and server-managed role profiles."""

import hmac
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.security import get_current_user, require_bearer_auth, require_role
from app.db.database import (
    get_db,
    set_database_security_context,
    set_onboarding_security_context,
)
from app.db.models import User, UserRole, Worker, WorkerType
from app.schemas.auth import (
    ProfileOut,
    StudentSignup,
    WardenSignup,
    WorkerSignup,
)
from app.utils.rate_limit import client_ip, signup_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/warden", tags=["Warden Auth"])
role_router = APIRouter(prefix="/auth", tags=["Authentication"])


def _profile(user: User, email: str) -> ProfileOut:
    return ProfileOut(id=user.id, name=user.name, email=email, role=user.role.value)


@router.get("/me", response_model=ProfileOut, summary="Get the signed-in Warden profile")
def warden_profile(
    auth_user: dict = Depends(require_bearer_auth),
    user: User = Depends(require_role(UserRole.WARDEN)),
) -> ProfileOut:
    return _profile(user, auth_user.get("email", ""))


@role_router.get("/me", response_model=ProfileOut, summary="Get the signed-in profile and role")
def current_profile(
    auth_user: dict = Depends(require_bearer_auth),
    user: User = Depends(get_current_user),
) -> ProfileOut:
    return _profile(user, auth_user.get("email", ""))


def _check_staff_invite_code(invite_code: str) -> None:
    """Gate Warden/Worker signup behind the server-side invite code.

    The code lives only in the backend environment (STAFF_INVITE_CODE). When it
    is unset, staff signup is disabled entirely. Comparison is constant-time.
    """
    expected = settings.staff_invite_code
    if not expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff signup is disabled.")
    supplied = (invite_code or "").strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid staff invite code is required.")


def _create_account(
    db: Session,
    *,
    email: str,
    password: str,
    name: str,
    role: UserRole,
    worker_type: WorkerType | None = None,
) -> ProfileOut:
    """Create a confirmed Supabase user and its role profile in one signup request."""
    auth_user = security.create_supabase_auth_user(email, password, name, role)
    try:
        auth_user_id = UUID(str(auth_user["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Supabase returned an invalid account identity.") from exc

    set_onboarding_security_context(db, auth_user_id)
    existing_account = bool(auth_user.pop("_hosteldesk_existing", False))
    linked = db.query(User).filter(User.auth_user_id == auth_user_id).one_or_none()
    if linked is not None:
        if linked.role is not role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is already linked to a different role.")
        return _profile(linked, email)

    metadata = auth_user.get("app_metadata")
    server_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    current_role = server_metadata.get("role")
    if current_role and current_role != role.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account already has a different HostelDesk role.")
    if existing_account and current_role != role.value:
        server_metadata["role"] = role.value
        security.update_supabase_app_metadata(auth_user_id, server_metadata)

    user = User(auth_user_id=auth_user_id, name=name, role=role)
    db.add(user)
    try:
        db.flush()
        if role is UserRole.WORKER:
            set_database_security_context(db, "SYSTEM")
            db.add(Worker(user_id=user.id, worker_type=worker_type or WorkerType.CLEANER))
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        if not existing_account:
            security.delete_supabase_auth_user(auth_user_id)
        logger.exception("Could not save the %s profile after Auth account creation", role.value)
        original = getattr(exc, "orig", exc)
        if getattr(original, "pgcode", None) == "42703" and "auth_user_id" in str(original):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "HostelDesk database migration 66ae9ccc1b8a is required before signup. "
                "Apply Alembic migrations with an owner-level database connection, then retry.",
            ) from exc
        raise HTTPException(status.HTTP_409_CONFLICT, "Account setup failed. Please try again.") from exc
    return _profile(user, email)


def _check_signup_rate_limit(request: Request) -> None:
    """Max 10 signups per hour per client IP (X-Forwarded-For first hop)."""
    from app.core.config import get_settings

    if not signup_limiter.check(
        f"signup:{client_ip(request)}", get_settings().signup_rate_limit_hourly, 3600
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-up attempts right now. Please try again in an hour.",
        )


@role_router.post("/student/signup", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def student_signup(payload: StudentSignup, request: Request, db: Session = Depends(get_db)) -> ProfileOut:
    _check_signup_rate_limit(request)
    return _create_account(
        db,
        email=payload.email.strip().casefold(),
        password=payload.password,
        name=payload.name.strip(),
        role=UserRole.STUDENT,
    )


@role_router.post("/warden/signup", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def warden_signup(payload: WardenSignup, request: Request, db: Session = Depends(get_db)) -> ProfileOut:
    _check_signup_rate_limit(request)
    _check_staff_invite_code(payload.invite_code)
    return _create_account(
        db,
        email=payload.email.strip().casefold(),
        password=payload.password,
        name=payload.name.strip(),
        role=UserRole.WARDEN,
    )


@role_router.post("/worker/signup", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def worker_signup(payload: WorkerSignup, request: Request, db: Session = Depends(get_db)) -> ProfileOut:
    _check_signup_rate_limit(request)
    _check_staff_invite_code(payload.invite_code)
    return _create_account(
        db,
        email=payload.email.strip().casefold(),
        password=payload.password,
        name=payload.name.strip(),
        role=UserRole.WORKER,
        worker_type=payload.worker_type,
    )
