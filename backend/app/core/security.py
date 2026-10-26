"""Authentication / authorisation primitives.

MVP demo authentication: the frontend sends the demo user id in the
``X-User-Id`` header. Real JWT auth can later be added by replacing
``get_current_user`` with a token-decoding dependency - every route already
depends on the user object, so no other change is needed.

Authorisation is always enforced server-side with ``require_role``.
"""

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserRole

_HEADER_NAME = "X-User-Id"


def _user_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unknown user. Send a valid X-User-Id header.",
    )


def get_current_user(
    x_user_id: int | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if x_user_id is None:
        raise _user_not_found()
    user = db.get(User, x_user_id)
    if user is None:
        raise _user_not_found()
    return user


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
