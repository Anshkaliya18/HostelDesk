"""Warden accounts are created as confirmed Supabase users with linked profiles."""

import uuid

from app.core import security
from app.db.models import User, UserRole
from tests.conftest import auth_header


def test_warden_profile_requires_supabase_bearer(client, seed_users):
    users = seed_users()
    response = client.get("/auth/warden/me", headers=auth_header(users["warden"]))
    assert response.status_code == 200
    assert response.json()["role"] == "WARDEN"
    legacy = client.get("/warden/dashboard", headers={"X-User-Id": str(users["warden"])} )
    assert legacy.status_code == 401


def test_warden_signup_creates_profile_in_one_request(client, db, monkeypatch):
    auth_id = uuid.uuid4()
    calls = []

    def create(email, password, name, role):
        calls.append((email, password, name, role))
        return {"id": str(auth_id), "email": email}

    monkeypatch.setattr(security, "create_supabase_auth_user", create)
    response = client.post("/auth/warden/signup", json={
        "name": "Warden Name", "email": "warden@example.test", "password": "long-password",
    })
    assert response.status_code == 201
    assert response.json()["role"] == "WARDEN"
    assert db.query(User).filter_by(auth_user_id=auth_id).one().role is UserRole.WARDEN
    assert calls == [("warden@example.test", "long-password", "Warden Name", UserRole.WARDEN)]
