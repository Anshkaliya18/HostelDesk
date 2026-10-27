"""Supabase Auth verification and server-side role authorization."""

from collections.abc import Callable
import logging
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
import httpx
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserRole

logger = logging.getLogger(__name__)

def _user_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in with your HostelDesk account to continue.",
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user = getattr(request.state, "current_user", None)
    if user is None:
        if getattr(request.state, "supabase_auth_user", None):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This Supabase account is not linked to a HostelDesk role.",
            )
        raise _user_not_found()
    if user.role == UserRole.WARDEN and not getattr(request.state, "supabase_auth_user", None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wardens must sign in with their Supabase account.",
        )
    return user


def parse_bearer_token(authorization: str) -> str:
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid Bearer token is required.")
    return token.strip()


def get_supabase_auth_user(access_token: str) -> dict:
    """Ask Supabase Auth to verify the access token; never trust decoded claims alone."""
    from app.core.config import settings

    if not settings.supabase_auth_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Supabase Auth is not configured on the server.",
        )
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_publishable_key, "Authorization": f"Bearer {access_token}"},
            timeout=8,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth is temporarily unavailable.") from exc
    if response.status_code in (401, 403):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session is invalid or expired.")
    if not response.is_success:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth could not verify the session.")
    return response.json()


def create_supabase_auth_user(email: str, password: str, name: str, role: UserRole) -> dict:
    """Create an immediately sign-in-ready account using server credentials."""
    from app.core.config import settings

    if not settings.supabase_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Admin API is not configured.")
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
                "app_metadata": {"role": role.value},
            },
            timeout=10,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth is temporarily unavailable.") from exc
    if response.status_code in (400, 409, 422):
        try:
            error_body = response.json()
        except ValueError:
            error_body = {}
        error_text = " ".join(
            str(error_body.get(key, ""))
            for key in ("message", "msg", "error", "error_code", "code", "error_description")
        ).casefold()
        duplicate = any(marker in error_text for marker in ("already registered", "already exists", "email_exists", "duplicate"))
        if duplicate:
            user = sign_in_supabase_auth_user(email, password)
            user["_hosteldesk_existing"] = True
            return user
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Supabase rejected the signup details.")
    if not response.is_success:
        logger.error("Supabase could not create an Auth user (HTTP %s)", response.status_code)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Supabase could not create the account.")
    return response.json()


def sign_in_supabase_auth_user(email: str, password: str) -> dict:
    """Verify ownership of an existing account before allowing profile recovery."""
    from app.core.config import settings

    if not settings.supabase_auth_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth is not configured.")
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
            headers={
                "apikey": settings.supabase_publishable_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
            timeout=10,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth is temporarily unavailable.") from exc
    if response.status_code in (400, 401, 422):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account already exists for this email. Sign in with its existing password to recover it.")
    if not response.is_success:
        logger.error("Supabase could not verify an existing Auth account (HTTP %s)", response.status_code)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Supabase could not verify the existing account.")
    body = response.json()
    user = body.get("user")
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Supabase returned an invalid account identity.")
    return user


def update_supabase_app_metadata(user_id: UUID, metadata: dict) -> None:
    """Set trusted role metadata through the server-only Supabase Admin API."""
    from app.core.config import settings

    if not settings.supabase_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Admin API is not configured.")
    try:
        response = httpx.put(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={"app_metadata": metadata},
            timeout=10,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Admin API is temporarily unavailable.") from exc
    if not response.is_success:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Supabase could not update the account role.")


def delete_supabase_auth_user(user_id: UUID) -> None:
    """Best-effort cleanup if profile creation fails after Auth user creation."""
    from app.core.config import settings

    try:
        response = httpx.delete(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            timeout=10,
        )
        if not response.is_success:
            logger.error("Supabase Auth user cleanup failed (HTTP %s)", response.status_code)
    except httpx.RequestError:
        logger.exception("Supabase Auth user cleanup request failed")


def require_bearer_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    auth_user = getattr(request.state, "supabase_auth_user", None)
    if auth_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with Supabase to continue.")
    return auth_user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Dependency that resolves the user and enforces their role."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            allowed = ", ".join(role.value for role in roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of the roles: {allowed}.",
            )
        return user

    return checker
