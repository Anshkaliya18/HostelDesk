"""Seed a realistic demo dataset for judges into the configured database.

Usage (from backend/):
    .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py [--reset-demo] [--yes]

Safety rules:
  - Photos come ONLY from backend/demo_assets/ (git-ignored). If it is empty,
    tiny placeholder JPEGs are generated locally with Pillow - no network.
  - Refuses to run against a remote/production-looking database (anything that
    is not sqlite) unless ``--yes`` is passed explicitly. ``--reset-demo``
    deletes existing demo complaints before reseeding and ALSO requires
    ``--yes``.
  - Idempotent: when the demo student already has complaints, the script
    reports and exits without duplicating anything.
"""

import argparse
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa

from app.core.config import settings
from app.db.database import SessionLocal, get_engine, set_database_security_context
from app.db.models import (
    AIRecommendation,
    Alert,
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

DEMO_ASSETS_DIR = Path(__file__).resolve().parents[1] / "demo_assets"

# (block, room, description, category, severity, age_days, with_photo)
DEMO_COMPLAINTS = [
    ("B", "203", "Ceiling fan in room 203 makes a grinding noise and stopped spinning.", "ELECTRICAL", "HIGH", 6, False),
    ("B", "205", "Bathroom tap drips constantly; the floor is always wet.", "PLUMBING", "MEDIUM", 5, True),
    ("B", "208", "Corridor light near room 208 is out; it is pitch dark at night.", "ELECTRICAL", "HIGH", 4, True),
    ("C", "112", "Water cooler on the C block first floor leaks water badly.", "PLUMBING", "MEDIUM", 3, True),
    ("C", "115", "Window latch broken in room 115, the room cannot be locked.", "FURNITURE", "MEDIUM", 2, True),
    ("A", "101", "Washroom drains are clogged and water is pooling in the corridor.", "CLEANING", "HIGH", 1, False),
    ("A", "104", "Study desk chair is broken - the back support snapped off.", "FURNITURE", "LOW", 1, False),
]

_DEMO_IDS = {
    "student": uuid.uuid5(uuid.NAMESPACE_URL, "hosteldesk-demo:student"),
    "warden": uuid.uuid5(uuid.NAMESPACE_URL, "hosteldesk-demo:warden"),
    "worker": uuid.uuid5(uuid.NAMESPACE_URL, "hosteldesk-demo:worker:electrician"),
}
_DEMO_NAMES = {"student": "Demo Student", "warden": "Demo Warden", "worker": "Demo Worker"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the HostelDesk demo dataset.")
    parser.add_argument("--reset-demo", action="store_true", help="Delete existing demo complaints first")
    parser.add_argument("--yes", action="store_true", help="Confirm non-sqlite targets and destructive reset")
    return parser.parse_args()


def _is_sqlite() -> bool:
    return (settings.database_url or "").lower().startswith("sqlite")


def _placeholder_photo(index: int) -> bytes:
    """Deterministic tiny placeholder JPEG via Pillow (no network)."""
    import io

    try:
        from PIL import Image

        palette = [(214, 234, 248), (234, 240, 229), (250, 242, 224)]
        rng = __import__("random").Random(index)
        image = Image.new("RGB", (320, 240), palette[index % len(palette)])
        for _ in range(24):
            x, y = rng.randrange(0, 300), rng.randrange(0, 220)
            image.paste((90, 80, 70), (x, y, x + 20, y + 20))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=70)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 - demo must also run without Pillow
        return b"\xff\xd8\xff\xe0" + b"JFIF" + b"\x00" * 16 + b"\xff\xd9"


def _photo_pool() -> list[bytes]:
    """Photo bytes for demo complaints - demo_assets only, never the network."""
    if DEMO_ASSETS_DIR.exists():
        photos = sorted(
            path for path in DEMO_ASSETS_DIR.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        if photos:
            return [path.read_bytes() for path in photos]
    DEMO_ASSETS_DIR.mkdir(exist_ok=True)
    return [_placeholder_photo(index) for index in range(6)]


def _store_photo(complaint, content: bytes) -> None:
    """Store through the app's storage layer so keys match production rules."""
    from app.utils.storage import get_image_storage

    key = get_image_storage().save(complaint.id, content, "jpg")
    complaint.photo_storage_key = key


def _seed_users(db: sa.orm.Session) -> dict[str, User]:
    users = {}
    roles = {
        "student": UserRole.STUDENT,
        "warden": UserRole.WARDEN,
        "worker": UserRole.WORKER,
    }
    for key, role in roles.items():
        auth_id = _DEMO_IDS[key]
        user = db.execute(
            sa.select(User).where(User.auth_user_id == auth_id)
        ).scalar_one_or_none()
        if user is None:
            user = User(name=_DEMO_NAMES[key], role=role, auth_user_id=auth_id)
            if role is UserRole.STUDENT:
                user.block = "B"
                user.room = "201"
            db.add(user)
            db.flush()
        if role is UserRole.WORKER:
            existing = db.execute(
                sa.select(Worker).where(Worker.user_id == user.id)
            ).scalar_one_or_none()
            if existing is None:
                db.add(Worker(user_id=user.id, worker_type=WorkerType.ELECTRICIAN))
                db.flush()
        users[key] = user
    db.commit()
    return users


def _has_demo_complaints(db: sa.orm.Session, users: dict[str, User]) -> bool:
    count = db.execute(
        sa.select(sa.func.count()).select_from(Complaint).where(
            Complaint.student_id == users["student"].id
        )
    ).scalar_one()
    return int(count) > 0


def _clear_existing_demo(db: sa.orm.Session, users: dict[str, User]) -> int:
    complaint_ids = db.execute(
        sa.select(Complaint.id).where(Complaint.student_id == users["student"].id)
    ).scalars().all()
    if not complaint_ids:
        return 0
    db.execute(sa.delete(Task).where(Task.complaint_id.in_(complaint_ids)))
    db.execute(sa.delete(StatusHistory).where(StatusHistory.complaint_id.in_(complaint_ids)))
    db.execute(sa.delete(AIRecommendation).where(AIRecommendation.complaint_id.in_(complaint_ids)))
    db.execute(sa.delete(Alert).where(Alert.block.in_(["A", "B", "C"])))
    db.execute(sa.delete(Complaint).where(Complaint.id.in_(complaint_ids)))
    db.commit()
    return len(complaint_ids)


def _add_history(db, complaint, old, new, created_at, changed_by=None, note=None):
    db.add(StatusHistory(
        complaint_id=complaint.id, old_status=old, new_status=new,
        changed_by=changed_by, note=note, created_at=created_at,
    ))


def _analyze(db, complaint, created_at, confidence="HIGH"):
    """Simulate the AI pipeline output exactly as production would store it."""
    trade = {
        "ELECTRICAL": WorkerType.ELECTRICIAN,
        "PLUMBING": WorkerType.PLUMBER,
        "CLEANING": WorkerType.CLEANER,
        "FURNITURE": WorkerType.CARPENTER,
    }[complaint.category.value]
    db.add(AIRecommendation(
        complaint_id=complaint.id, category=complaint.category,
        severity=complaint.severity, suggested_worker=trade,
        confidence=confidence, model="gemini-2.5-flash",
        reason=f"{complaint.category.value.capitalize()} report needing attention",
        raw_response={
            "category": complaint.category.value,
            "severity": complaint.severity.value,
            "suggested_worker": trade.value,
        },
        created_at=created_at + timedelta(seconds=40),
    ))
    complaint.ai_suggested_worker = trade
    _add_history(db, complaint, None, ComplaintStatus.SUBMITTED, created_at,
                 changed_by=complaint.student_id, note="Complaint submitted")
    _add_history(db, complaint, ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED,
                 created_at + timedelta(seconds=60), note="AI analysis")
    _add_history(db, complaint, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW,
                 created_at + timedelta(seconds=90), note="Ready for warden review")


def _seed_complaints(db: sa.orm.Session, users: dict[str, User], photos: list[bytes]) -> int:
    student = users["student"]
    warden = users["warden"]
    worker_row = db.execute(
        sa.select(Worker).where(Worker.user_id == users["worker"].id)
    ).scalar_one_or_none()
    if worker_row is None:
        worker_row = Worker(user_id=users["worker"].id, worker_type=WorkerType.ELECTRICIAN)
        db.add(worker_row)
        db.flush()

    now = utcnow()
    created = 0

    # 7 complaints sitting in WARDEN_REVIEW with a live AI recommendation.
    for index, (block, room, description, category, severity, age_days, with_photo) in enumerate(
        DEMO_COMPLAINTS
    ):
        created_at = now - timedelta(days=age_days, hours=index % 6 + 1)
        complaint = Complaint(
            student_id=student.id, block=block, room=room, description=description,
            created_at=created_at, status=ComplaintStatus.WARDEN_REVIEW,
        )
        db.add(complaint)
        db.flush()
        complaint.category = ComplaintCategory[category]
        complaint.severity = Severity[severity]
        _analyze(db, complaint, created_at)
        if with_photo and photos:
            _store_photo(complaint, photos[index % len(photos)])
        created += 1

    # One assigned + in-progress electrical job for the demo worker.
    complaint = Complaint(
        student_id=student.id, block="B", room="201",
        description="Buzzer at the B block entrance keeps ringing by itself.",
        created_at=now - timedelta(days=2), status=ComplaintStatus.IN_PROGRESS,
    )
    db.add(complaint)
    db.flush()
    complaint.category = ComplaintCategory.ELECTRICAL
    complaint.severity = Severity.MEDIUM
    complaint.approved_worker_id = worker_row.id
    _analyze(db, complaint, now - timedelta(days=2))
    _add_history(db, complaint, ComplaintStatus.WARDEN_REVIEW, ComplaintStatus.ASSIGNED,
                 now - timedelta(days=2) + timedelta(minutes=30), changed_by=warden.id,
                 note="Assigned to the electrician")
    db.add(Task(
        complaint_id=complaint.id, worker_id=worker_row.id,
        status=TaskStatus.IN_PROGRESS,
        assigned_at=now - timedelta(days=2) + timedelta(minutes=30),
        started_at=now - timedelta(days=1),
    ))
    _add_history(db, complaint, ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS,
                 now - timedelta(days=1), note="started repair")
    _store_photo(complaint, photos[0])
    created += 1

    # One completed complaint a few hours ago => the digest shows "completed today".
    complaint = Complaint(
        student_id=student.id, block="A", room="102",
        description="Mess hall handwash dispenser was leaking soap onto the floor.",
        created_at=now - timedelta(days=2), status=ComplaintStatus.COMPLETED,
    )
    db.add(complaint)
    db.flush()
    complaint.category = ComplaintCategory.CLEANING
    complaint.severity = Severity.LOW
    complaint.approved_worker_id = worker_row.id
    complaint.warden_note = "Routine cleaning issue - handled by housekeeping."
    complaint.worker_note = "Cleaned and resealed the dispenser unit."
    _analyze(db, complaint, now - timedelta(days=2))
    completed_at = now - timedelta(hours=5)
    complaint.completed_at = completed_at
    db.add(Task(
        complaint_id=complaint.id, worker_id=worker_row.id, status=TaskStatus.COMPLETED,
        assigned_at=now - timedelta(days=2) + timedelta(minutes=20),
        started_at=now - timedelta(days=1), completed_at=completed_at,
        note="Cleaned and resealed the dispenser unit.",
    ))
    _add_history(db, complaint, ComplaintStatus.WARDEN_REVIEW, ComplaintStatus.ASSIGNED,
                 now - timedelta(days=1) + timedelta(minutes=20), changed_by=warden.id,
                 note="Assigned to the cleaner")
    _add_history(db, complaint, ComplaintStatus.IN_PROGRESS, ComplaintStatus.COMPLETED,
                 completed_at, note="Cleaned and resealed the dispenser unit.")
    _store_photo(complaint, photos[1])
    created += 1

    db.commit()
    return created


def main() -> int:
    args = _parse_args()
    if not _is_sqlite() and not args.yes:
        print(
            "Refusing to seed: DATABASE_URL does not look like a local sqlite database.\n"
            "Point DATABASE_URL at a disposable local sqlite database, or pass --yes\n"
            "explicitly to confirm writing this dataset into the configured database."
        )
        return 2

    Base.metadata.create_all(get_engine())

    db = SessionLocal()
    set_database_security_context(db, "SYSTEM")
    photos = _photo_pool()
    try:
        users = _seed_users(db)
        removed = 0
        if args.reset_demo:
            if not args.yes:
                print("--reset-demo also requires --yes (it deletes demo complaints).")
                return 2
            removed = _clear_existing_demo(db, users)
        elif _has_demo_complaints(db, users):
            print(
                "Demo data already present for the demo student - nothing to do.\n"
                "Use --reset-demo --yes to rebuild the demo dataset."
            )
            return 0
        created = _seed_complaints(db, users, photos)
        print(f"Seed complete: {created} demo complaints created "
              f"({removed} removed by --reset-demo).")
        print("Demo user rows carry deterministic identities (hosteldesk-demo:*).")
        print("Sign-in needs matching Supabase Auth users on the demo project.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
