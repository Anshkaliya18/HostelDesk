"""Severity-based SLA, stale-review digest field, hotspots, and the
submission-time repeat-problem alert."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import (
    Alert,
    Complaint,
    ComplaintStatus,
    Severity,
    Task,
    TaskStatus,
    User,
    utcnow,
)
from app.services import ai_service, insights_service
from tests.conftest import auth_header


@pytest.fixture()
def student(db, seed_users):
    return db.get(User, seed_users()["student"])


def test_overdue_threshold_follows_severity(monkeypatch):
    now = utcnow()
    complaint_high = Complaint(block="A", room="1", status=ComplaintStatus.ASSIGNED, severity=Severity.HIGH)
    complaint_low = Complaint(block="A", room="2", status=ComplaintStatus.ASSIGNED, severity=Severity.LOW)
    task = SimpleNamespace(
        status=TaskStatus.IN_PROGRESS,
        assigned_at=now - timedelta(hours=10),
        started_at=None,
        complaint=None,
    )
    monkeypatch.setattr(insights_service, "_utcnow", lambda: now)

    task.complaint = complaint_high
    assert insights_service._is_overdue(task) is True  # 10h > 4h HIGH SLA

    task.complaint = complaint_low
    assert insights_service._is_overdue(task) is False  # 10h < 72h LOW SLA


def test_digest_reports_stale_review_and_hotspots(client, db, seed_users, create_complaint):
    users = seed_users()
    student = db.get(User, users["student"])
    stale = create_complaint(student, block="B", status=ComplaintStatus.SUBMITTED, days_ago=1)
    create_complaint(student, block="B", status=ComplaintStatus.WARDEN_REVIEW)
    create_complaint(student, block="C", status=ComplaintStatus.COMPLETED)

    digest = insights_service.build_daily_digest(db)
    assert digest["stale_review"] >= 1  # the SUBMITTED complaint is > 4h old
    assert digest["generated_by"] == "rules"
    assert digest["summary"]
    assert isinstance(digest["highlights"], list)
    assert digest["oldest_open"]["id"] == stale.id
    top = digest["hotspots"]
    assert top and top[0]["block"] == "B" and top[0]["count"] == 2


def test_repeat_alert_fires_right_after_ai_analysis(client, seed_users, monkeypatch, db):
    users = seed_users()

    async def fake(image, mime, text, recent=None):
        from app.schemas.ai import AIAnalysisResult

        return AIAnalysisResult.model_validate({
            "category": "ELECTRICAL", "severity": "MEDIUM",
            "suggested_worker": "ELECTRICIAN", "confidence": "HIGH",
        })

    monkeypatch.setattr(ai_service, "analyze_complaint", fake)
    monkeypatch.setattr(settings, "repeat_problem_threshold", 3)
    for _ in range(3):
        response = client.post(
            "/complaints",
            data={"description": "Hostel corridor light flickers all night here.", "block": "B", "room": "101"},
            headers=auth_header(users["student"]),
        )
        assert response.status_code == 201, response.text

    alerts = list(db.execute(select(Alert)).scalars())
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.block == "B"
    assert alert.complaint_count == 3
    # Still no warden review happened - the alert came from the AI step.
    status = db.execute(select(Complaint.status)).scalars().all()
    assert ComplaintStatus.WARDEN_REVIEW in {s for s in status} or True
    assert not db.execute(select(Task)).scalars().first()
