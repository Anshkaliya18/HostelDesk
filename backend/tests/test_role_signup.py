"""Role signups create confirmed Supabase identities and linked profiles in one request."""

import uuid
from types import SimpleNamespace

from sqlalchemy.exc import ProgrammingError

from app.core import security
from app.core.config import settings
from app.db.database import get_db
from app.db.models import User, UserRole, Worker, WorkerType


def _stub_create(monkeypatch, auth_id):
    calls = []

    def create(email, password, name, role):
        calls.append((email, password, name, role))
        return {"id": str(auth_id), "email": email, "email_confirmed_at": "now",
                "app_metadata": {"role": role.value}}

    monkeypatch.setattr(security, "create_supabase_auth_user", create)
    return calls


def test_student_signup_creates_profile_without_confirmation_step(client, db, monkeypatch):
    auth_id = uuid.uuid4()
    calls = _stub_create(monkeypatch, auth_id)
    response = client.post("/auth/student/signup", json={
        "name": "Student Name", "email": " Student@Example.test ", "password": "long-password",
    })
    assert response.status_code == 201
    assert response.json()["role"] == "STUDENT"
    assert db.query(User).filter_by(auth_user_id=auth_id).one().role is UserRole.STUDENT
    assert calls == [("student@example.test", "long-password", "Student Name", UserRole.STUDENT)]


def test_worker_signup_creates_worker_profile(client, db, monkeypatch):
    monkeypatch.setattr(settings, "staff_invite_code", "worker-secret")
    auth_id = uuid.uuid4()
    _stub_create(monkeypatch, auth_id)
    response = client.post("/auth/worker/signup", json={
        "name": "Worker Name", "email": "worker@example.test", "password": "long-password",
        "worker_type": "ELECTRICIAN", "invite_code": "worker-secret",
    })
    assert response.status_code == 201
    user = db.query(User).filter_by(auth_user_id=auth_id).one()
    worker = db.query(Worker).filter_by(user_id=user.id).one()
    assert user.role is UserRole.WORKER
    assert worker.worker_type is WorkerType.ELECTRICIAN


def test_supabase_admin_signup_confirms_email_and_sets_server_role(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-key")
    calls = {}

    def post(url, **kwargs):
        calls.update(url=url, **kwargs)
        return SimpleNamespace(status_code=201, is_success=True, json=lambda: {"id": str(uuid.uuid4())})

    monkeypatch.setattr(security.httpx, "post", post)
    security.create_supabase_auth_user("student@example.test", "safe-password", "Student", UserRole.STUDENT)
    assert calls["json"]["email_confirm"] is True
    assert calls["json"]["app_metadata"] == {"role": "STUDENT"}
    assert calls["headers"]["Authorization"] == "Bearer server-only-key"


def test_signup_validation_does_not_echo_password(client):
    response = client.post("/auth/student/signup", json={
        "name": "Student", "email": "student@example.test", "password": "secret",
    })
    assert response.status_code == 422
    assert "secret" not in response.text


def test_signup_reports_missing_auth_link_migration(client, db, monkeypatch):
    auth_id = uuid.uuid4()
    monkeypatch.setattr(security, "create_supabase_auth_user", lambda *_args: {"id": str(auth_id)})
    monkeypatch.setattr(security, "delete_supabase_auth_user", lambda *_args: None)
    database_error = Exception("column users.auth_user_id does not exist")
    database_error.pgcode = "42703"
    monkeypatch.setattr(db, "flush", lambda: (_ for _ in ()).throw(ProgrammingError("INSERT", {}, database_error)))

    def override_db():
        yield db

    client.app.dependency_overrides[get_db] = override_db
    try:
        response = client.post("/auth/student/signup", json={
            "name": "Student", "email": "student@example.test", "password": "long-password",
        })
    finally:
        client.app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert "migration 66ae9ccc1b8a" in response.json()["detail"]


def test_signup_retry_links_an_existing_auth_user_after_password_verification(client, db, monkeypatch):
    auth_id = uuid.uuid4()
    monkeypatch.setattr(security, "create_supabase_auth_user", lambda *_args: {
        "id": str(auth_id), "app_metadata": {"provider": "email"}, "_hosteldesk_existing": True,
    })
    metadata_updates = []
    monkeypatch.setattr(security, "update_supabase_app_metadata",
                        lambda user_id, metadata: metadata_updates.append((user_id, metadata)))
    deleted = []
    monkeypatch.setattr(security, "delete_supabase_auth_user", lambda user_id: deleted.append(user_id))

    response = client.post("/auth/student/signup", json={
        "name": "Student Name", "email": "student@example.test", "password": "long-password",
    })
    assert response.status_code == 201
    assert response.json()["role"] == "STUDENT"
    assert db.query(User).filter_by(auth_user_id=auth_id).one().role is UserRole.STUDENT
    assert metadata_updates == [(auth_id, {"provider": "email", "role": "STUDENT"})]
    assert deleted == []


# ---- Staff invite code ----


def test_staff_signup_disabled_without_invite_code(client, monkeypatch):
    monkeypatch.setattr(settings, "staff_invite_code", "")
    response = client.post("/auth/warden/signup", json={
        "name": "Warden Name", "email": "warden@example.test", "password": "long-password",
        "invite_code": "anything",
    })
    assert response.status_code == 403
    assert response.json()["detail"] == "Staff signup is disabled."
    assert client.post("/auth/worker/signup", json={
        "name": "Worker Name", "email": "worker@example.test", "password": "long-password",
        "worker_type": "PLUMBER", "invite_code": "anything",
    }).status_code == 403


def test_staff_signup_requires_matching_invite_code(client, monkeypatch):
    monkeypatch.setattr(settings, "staff_invite_code", "real-code")
    bad = client.post("/auth/warden/signup", json={
        "name": "Warden Name", "email": "warden@example.test", "password": "long-password",
    })
    assert bad.status_code == 403
    wrong = client.post("/auth/worker/signup", json={
        "name": "Worker Name", "email": "worker@example.test", "password": "long-password",
        "worker_type": "PLUMBER", "invite_code": "wrong-code",
    })
    assert wrong.status_code == 403
    # No Supabase user may have been created for rejected attempts.
    assert db_is_empty()


def test_student_signup_stays_open_without_invite_code(client, monkeypatch):
    monkeypatch.setattr(settings, "staff_invite_code", "")
    auth_id = uuid.uuid4()
    monkeypatch.setattr(security, "create_supabase_auth_user",
                        lambda *_args: {"id": str(auth_id), "app_metadata": {"role": "STUDENT"}})
    response = client.post("/auth/student/signup", json={
        "name": "Student Name", "email": "open.student@example.test", "password": "long-password",
    })
    assert response.status_code == 201
    assert response.json()["role"] == "STUDENT"


def db_is_empty() -> bool:
    from app.db.database import SessionLocal
    from app.db.models import User

    session = SessionLocal()
    try:
        return session.query(User).count() == 0
    finally:
        session.close()
