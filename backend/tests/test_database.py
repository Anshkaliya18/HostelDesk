"""Database-layer tests: connectivity, model integrity, foreign keys."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import get_engine
from app.db.models import (
    AIRecommendation,
    Alert,
    AlertType,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Severity,
    User,
    UserRole,
    Worker,
    WorkerType,
)


def test_engine_connects_and_selects_one():
    with get_engine().connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1


def test_role_enum_round_trip(db, client):
    user = User(name="RBAC User", role=UserRole.WARDEN)
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.role is UserRole.WARDEN
    assert user.created_at.tzinfo is None or isinstance(user.created_at, datetime)


def test_worker_type_enum_round_trip(db):
    user = User(name="Worker Enum", role=UserRole.WORKER)
    db.add(user)
    db.flush()
    worker = Worker(user_id=user.id, worker_type=WorkerType.CARPENTER)
    db.add(worker)
    db.commit()
    db.refresh(worker)
    assert worker.worker_type is WorkerType.CARPENTER
    assert worker.is_active is True  # server-side default


def test_foreign_key_rejects_complaint_for_missing_student(db):
    with pytest.raises(IntegrityError):
        complaint = Complaint(
            student_id=99999,
            description="Fan in room 12 is completely dead since yesterday morning.",
            block="D",
            room="12",
            status=ComplaintStatus.SUBMITTED,
        )
        db.add(complaint)
        db.commit()


def test_foreign_key_rejects_recommendation_for_missing_complaint(db):
    with pytest.raises(IntegrityError):
        db.add(
            AIRecommendation(
                complaint_id=99999,
                category=ComplaintCategory.ELECTRICAL,
                severity=Severity.HIGH,
                suggested_worker=WorkerType.ELECTRICIAN,
                raw_response={"category": "electrical"},
            )
        )
        db.commit()


def test_alert_defaults(db):
    alert = Alert(
        alert_type=AlertType.REPEAT_PROBLEM,
        block="A",
        category=ComplaintCategory.ELECTRICAL,
        complaint_count=3,
        message="ELECTRICAL issues repeat in A Block: 3 complaints in the last 7 days.",
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    assert alert.resolved_at is None
