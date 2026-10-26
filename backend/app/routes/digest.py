"""Digest endpoint: deterministic daily summary for the warden (no AI)."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import insights_service

router = APIRouter(prefix="/digest", tags=["Digest"])


class DigestOut(BaseModel):
    date: str
    open_complaints: int
    overdue_complaints: int
    completed_complaints: int
    recurring_issues: int
    category_counts: dict[str, int]


@router.get("", response_model=DigestOut, summary="Daily warden digest (deterministic)")
def daily_digest(
    date: date | None = Query(default=None, description="ISO date, defaults to today (UTC)"),
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> DigestOut:
    digest = insights_service.build_daily_digest(db, date)
    return DigestOut(**digest)
