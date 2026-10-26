"""Shared pytest fixtures for HostelDesk backend tests."""

import os
import shutil
import tempfile
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from base64 import b64decode
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The test database and external services must be configured before any app
# module is imported. Forcing empty strings keeps tests hermetic/no network
# even when the real backend/.env carries Supabase or Gemini credentials.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
_TEST_UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="hosteldesk-test-uploads-"))
os.environ["UPLOAD_DIR"] = str(_TEST_UPLOAD_DIR)

from app.db.database import get_engine, SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Base,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Severity,
    User,
    UserRole,
    Worker,
    WorkerType,
    utcnow,
)
from app.core import security  # noqa: E402
from app.main import app  # noqa: E402


def png_bytes() -> bytes:
    """1x1 transparent PNG (valid magic bytes)."""
    return b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgY"
        "GBgAAAABQABh6fo1wAAAABJRU5ErkJggg=="
    )


def jpeg_bytes() -> bytes:
    """Minimal JPEG magic-byte payload accepted by the storage validator."""
    return b"\xff\xd8\xff\xe0" + b"JFIF" + b"\x00" * 16 + b"\xff\xd9"


def auth_header(user_id: int | None) -> dict[str, str]:
    return {"Authorization": f"Bearer test-user:{user_id}"}


@pytest.fixture(autouse=True)
def _stub_supabase_auth(monkeypatch):
    """Keep API tests offline while exercising the Bearer-auth code path."""
    def authenticate(token: str) -> dict:
        if not token.startswith("test-user:"):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Invalid test session")
        raw_id = token.split(":", 1)[1]
        try:
            auth_id = uuid.UUID(raw_id)
        except ValueError:
            auth_id = uuid.UUID(int=int(raw_id))
        return {
            "id": str(auth_id),
            "email": f"test-{auth_id.int}@example.test",
            "app_metadata": {},
        }

    monkeypatch.setattr(security, "get_supabase_auth_user", authenticate)


@pytest.fixture(autouse=True)
def _clean_test_uploads():
    """Isolate local-storage file state between tests."""
    complaints_dir = _TEST_UPLOAD_DIR / "complaints"
    shutil.rmtree(complaints_dir, ignore_errors=True)
    yield
    shutil.rmtree(complaints_dir, ignore_errors=True)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Fresh table set for every test."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seed_users(db) -> Callable[[], dict[str, int]]:
    """Two demo worker profiles; returns all relevant ids."""

    def _seed() -> dict[str, int]:
        student = User(name="Student One", role=UserRole.STUDENT, block="A", room="101")
        warden = User(name="Warden Demo", role=UserRole.WARDEN)
        worker_user_one = User(name="Worker One", role=UserRole.WORKER)
        worker_user_two = User(name="Worker Two", role=UserRole.WORKER)
        db.add_all([student, warden, worker_user_one, worker_user_two])
        db.flush()
        for user in (student, warden, worker_user_one, worker_user_two):
            user.auth_user_id = uuid.UUID(int=user.id)
        electrician = Worker(user_id=worker_user_one.id, worker_type=WorkerType.ELECTRICIAN)
        plumber = Worker(user_id=worker_user_two.id, worker_type=WorkerType.PLUMBER)
        db.add_all([electrician, plumber])
        db.commit()
        return {
            "student": student.id,
            "warden": warden.id,
            "worker_electrician_user": worker_user_one.id,
            "worker_plumber_user": worker_user_two.id,
            "electrician": electrician.id,
            "plumber": plumber.id,
        }

    return _seed


@pytest.fixture()
def create_complaint(db) -> Callable[..., Complaint]:
    """Create a complaint row directly (bypasses the API/AI path)."""

    def _create(
        student: User,
        block: str = "A",
        category: ComplaintCategory | None = ComplaintCategory.ELECTRICAL,
        severity: Severity | None = Severity.MEDIUM,
        status: ComplaintStatus = ComplaintStatus.WARDEN_REVIEW,
        days_ago: int = 0,
    ) -> Complaint:
        complaint = Complaint(
            student_id=student.id,
            description="Ceiling fan in room 204 stopped working entirely.",
            block=block,
            room="204",
            category=category,
            severity=severity,
            ai_suggested_worker=WorkerType.ELECTRICIAN
            if category == ComplaintCategory.ELECTRICAL
            else None,
            status=status,
            created_at=utcnow() - timedelta(days=days_ago),
        )
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        return complaint

    return _create
