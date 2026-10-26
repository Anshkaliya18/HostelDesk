"""Seed the HostelDesk database with clearly fake demo data.

Usage (run from backend/):
    python seed.py            # seeds only when the database is empty
    python seed.py --reset    # drops and recreates all tables, then seeds

Demo users: 2 students, 1 warden, 4 workers. No real personal information.
"""

import sys
from datetime import timedelta

from app.core.config import settings
from app.db.database import get_engine, SessionLocal, system_database_context
from app.db.models import (
    AIRecommendation,
    Alert,
    AlertType,
    Base,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Severity,
    StatusHistory,
    Task,
    TaskStatus,
    User,
    UserRole,
    Worker,
    WorkerType,
    utcnow,
)
from sqlalchemy import select


def _days_ago(days: int):
    return utcnow() - timedelta(days=days)


def _reset(db_sessionmaker) -> None:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed(reset: bool) -> None:
    if reset:
        _reset(SessionLocal)

    with SessionLocal() as db, system_database_context(db):
        if db.execute(select(User)).first() is not None:
            print("Database already seeded. Use --reset to drop and reseed.")
            return

        # ---- Users --------------------------------------------------------
        student_arya = User(name="Demo Student Arya", role=UserRole.STUDENT, block="A", room="204")
        student_rohan = User(name="Demo Student Rohan", role=UserRole.STUDENT, block="C", room="112")
        warden = User(name="Demo Warden Meera", role=UserRole.WARDEN)
        db.add_all([student_arya, student_rohan, warden])
        db.flush()

        workers = [
            Worker(user=User(name="Demo Worker Ramu", role=UserRole.WORKER), worker_type=WorkerType.ELECTRICIAN),
            Worker(user=User(name="Demo Worker Suresh", role=UserRole.WORKER), worker_type=WorkerType.PLUMBER),
            Worker(user=User(name="Demo Worker Kamla", role=UserRole.WORKER), worker_type=WorkerType.CLEANER),
            Worker(user=User(name="Demo Worker Bhola", role=UserRole.WORKER), worker_type=WorkerType.CARPENTER),
        ]
        db.add_all(workers)
        db.flush()
        electrician, plumber, cleaner, carpenter = workers

        # ---- Complaints ---------------------------------------------------
        # 1) repeat-problem trigger: 3x ELECTRICAL in A block inside 7 days
        c1 = Complaint(student_id=student_arya.id, description="Ceiling fan sparking and rattling in room 204.", block="A", room="204", category=ComplaintCategory.ELECTRICAL, severity=Severity.HIGH, ai_suggested_worker=WorkerType.ELECTRICIAN, status=ComplaintStatus.COMPLETED, created_at=_days_ago(9), completed_at=_days_ago(8))
        c2 = Complaint(student_id=student_rohan.id, description="Tube light flickering in the corridor outside room 112.", block="A", room="112", category=ComplaintCategory.ELECTRICAL, severity=Severity.MEDIUM, ai_suggested_worker=WorkerType.ELECTRICIAN, status=ComplaintStatus.COMPLETED, created_at=_days_ago(4), completed_at=_days_ago(3))
        c3 = Complaint(student_id=student_arya.id, description="Power socket in room 204 is dead since last night.", block="A", room="204", category=ComplaintCategory.ELECTRICAL, severity=Severity.HIGH, ai_suggested_worker=WorkerType.ELECTRICIAN, status=ComplaintStatus.ASSIGNED, created_at=_days_ago(1))
        c4 = Complaint(student_id=student_rohan.id, description="Bathroom tap leaking continuously in room 112.", block="C", room="112", category=ComplaintCategory.PLUMBING, severity=Severity.MEDIUM, ai_suggested_worker=WorkerType.PLUMBER, status=ComplaintStatus.WARDEN_REVIEW, created_at=_days_ago(2))
        db.add_all([c1, c2, c3, c4])
        db.flush()

        # Persist the original AI recommendation for each analysed complaint
        # (the warden decision lives on the complaint, never in this table).
        for complaint, category, severity, worker in [
            (c1, ComplaintCategory.ELECTRICAL, Severity.HIGH, WorkerType.ELECTRICIAN),
            (c2, ComplaintCategory.ELECTRICAL, Severity.MEDIUM, WorkerType.ELECTRICIAN),
            (c3, ComplaintCategory.ELECTRICAL, Severity.HIGH, WorkerType.ELECTRICIAN),
            (c4, ComplaintCategory.PLUMBING, Severity.MEDIUM, WorkerType.PLUMBER),
        ]:
            db.add(
                AIRecommendation(
                    complaint_id=complaint.id,
                    category=category,
                    severity=severity,
                    suggested_worker=worker,
                    raw_response={"category": category.value, "severity": severity.value, "suggested_worker": worker.value},
                )
            )

        # ---- Tasks + history ------------------------------------------------
        db.add_all(
            [
                StatusHistory(complaint_id=c2.id, old_status=None, new_status=ComplaintStatus.SUBMITTED, changed_by=student_rohan.id, note="Submitted"),
                StatusHistory(complaint_id=c2.id, old_status=ComplaintStatus.WARDEN_REVIEW, new_status=ComplaintStatus.ASSIGNED, changed_by=warden.id, note="Assigned to electrician"),
                StatusHistory(complaint_id=c2.id, old_status=ComplaintStatus.ASSIGNED, new_status=ComplaintStatus.IN_PROGRESS, changed_by=electrician.user_id, note="Started work"),
                StatusHistory(complaint_id=c2.id, old_status=ComplaintStatus.IN_PROGRESS, new_status=ComplaintStatus.COMPLETED, changed_by=electrician.user_id, note="Replaced tube light"),
            ]
        )
        db.add(
            Task(
                complaint_id=c1.id, worker_id=electrician.id, status=TaskStatus.COMPLETED,
                note="Rewired the fan connection.", assigned_at=_days_ago(9),
                started_at=_days_ago(9) + timedelta(hours=3), completed_at=_days_ago(8),
            )
        )
        db.add(
            Task(
                complaint_id=c2.id, worker_id=electrician.id, status=TaskStatus.COMPLETED,
                note="Replaced the tube light.", assigned_at=_days_ago(4),
                started_at=_days_ago(4) + timedelta(hours=2), completed_at=_days_ago(3),
            )
        )
        db.add(
            Task(
                complaint_id=c3.id, worker_id=electrician.id, status=TaskStatus.ASSIGNED,
                assigned_at=_days_ago(1),
            )
        )
        db.add(
            StatusHistory(
                complaint_id=c3.id, old_status=ComplaintStatus.WARDEN_REVIEW,
                new_status=ComplaintStatus.ASSIGNED, changed_by=warden.id, note="Urgent repair",
            )
        )

        # Repeat-problem alert for A block / ELECTRICAL (3 complaints in window).
        db.add(
            Alert(
                alert_type=AlertType.REPEAT_PROBLEM,
                block="A",
                category=ComplaintCategory.ELECTRICAL,
                complaint_count=3,
                message="ELECTRICAL issues repeat in A Block: 3 complaints in the last 7 days.",
                created_at=_days_ago(1),
            )
        )

        db.commit()

    print("Seed complete:")
    print(f"  X-User-Id {student_arya.id}/{student_rohan.id} = students (Arya, Rohan)")
    print(f"  X-User-Id {warden.id} = warden (Meera)")
    print(f"  X-User-Id {electrician.user_id}/{plumber.user_id}/{cleaner.user_id}/{carpenter.user_id} = workers (Ramu electrician, Suresh plumber, Kamla cleaner, Bhola carpenter)")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
