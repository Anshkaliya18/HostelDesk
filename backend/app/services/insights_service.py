"""Insights / rules service: deterministic repeat-problem alerts + daily digest.

No AI here. Everything is plain database rules so the warden digest never
depends on Gemini.
"""

import logging
from datetime import date, timedelta, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Alert,
    AlertType,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware ones. Normalize."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def evaluate_repeat_problem(db: Session, complaint: Complaint) -> Alert | None:
    """Rule: 3+ complaints for the same (block, category) inside the window
    create (or refresh) one REPEAT_PROBLEM alert."""
    if complaint.category is None:
        return None

    window_start = _utcnow() - timedelta(days=settings.repeat_problem_window_days)
    count_stmt = select(func.count()).select_from(Complaint).where(
        Complaint.block == complaint.block,
        Complaint.category == complaint.category,
        Complaint.created_at >= window_start,
    )
    complaint_count = int(db.execute(count_stmt).scalar_one())

    existing = db.execute(
        select(Alert).where(
            Alert.block == complaint.block,
            Alert.category == complaint.category,
            Alert.resolved_at.is_(None),
        )
    ).scalar_one_or_none()

    if complaint_count < settings.repeat_problem_threshold:
        return existing

    window_days = settings.repeat_problem_window_days
    if existing is None:
        alert = Alert(
            alert_type=AlertType.REPEAT_PROBLEM,
            block=complaint.block,
            category=complaint.category,
            complaint_count=complaint_count,
            message=(
                f"{complaint.category.value} issues repeat in {complaint.block} Block: "
                f"{complaint_count} complaints in the last {window_days} days."
            ),
        )
        db.add(alert)
        db.flush()
        logger.info(
            "Repeat-problem alert generated for %s / %s (count=%d)",
            complaint.block,
            complaint.category.value,
            complaint_count,
        )
        return alert

    existing.complaint_count = complaint_count
    existing.message = (
        f"{complaint.category.value} issues repeat in {existing.block} Block: "
        f"{complaint_count} complaints in the last {window_days} days."
    )
    db.flush()
    return existing


def list_active_alerts(db: Session) -> list[Alert]:
    stmt = (
        select(Alert)
        .where(Alert.resolved_at.is_(None))
        .order_by(Alert.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def _is_overdue(task: Task) -> bool:
    if task.status not in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
        return False
    threshold = _utcnow() - timedelta(hours=settings.task_overdue_hours)
    reference = task.started_at or task.assigned_at
    if reference is None:
        return False
    return _as_utc(reference) < threshold


def build_daily_digest(db: Session, day: date | None = None) -> dict:
    """Deterministic daily summary for the warden. Plain DB rules only."""
    if day is None:
        day = _utcnow().date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    complaints = db.execute(select(Complaint)).scalars().all()

    open_complaints = [c for c in complaints if c.status != ComplaintStatus.COMPLETED]

    overdue_complaints = []
    for complaint in complaints:
        for task in complaint.tasks if complaint.tasks else []:
            if _is_overdue(task):
                overdue_complaints.append(complaint)
                break

    completed_today = [
        c
        for c in complaints
        if c.completed_at is not None and day_start <= _as_utc(c.completed_at) < day_end
    ]
    created_today = [c for c in complaints if day_start <= _as_utc(c.created_at) < day_end]

    category_counts = {category.value: 0 for category in ComplaintCategory}
    for complaint in created_today:
        if complaint.category is not None:
            category_counts[complaint.category.value] += 1

    recurring = list_active_alerts(db)

    return {
        "date": day.isoformat(),
        "open_complaints": len(open_complaints),
        "overdue_complaints": len(overdue_complaints),
        "completed_complaints": len(completed_today),
        "recurring_issues": len(recurring),
        "category_counts": category_counts,
    }
