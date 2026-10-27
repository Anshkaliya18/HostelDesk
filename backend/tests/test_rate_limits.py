"""Abuse limits: per-student complaint windows and per-IP signup window."""

from app.core import security
from app.core.config import settings
from app.utils import rate_limit

from tests.conftest import auth_header, jpeg_bytes

_DESCRIPTION = "Ceiling fan sparking loudly in room 204 since Monday morning."


def _submit(client, users, *, index=0):
    return client.post(
        "/complaints",
        data={
            "description": f"{_DESCRIPTION} Report number {index}.",
            "block": "A",
            "room": "204",
        },
        files={"photo": ("fan.jpg", jpeg_bytes(), "image/jpeg")},
        headers=auth_header(users["student"]),
    )


def test_complaint_submission_limited_to_5_per_10_minutes(client, seed_users, monkeypatch):
    users = seed_users()
    for index in range(5):
        response = _submit(client, users, index=index)
        assert response.status_code == 201, response.text

    sixth = _submit(client, users, index=6)
    assert sixth.status_code == 429
    assert "wait a few minutes" in sixth.json()["detail"]


def test_complaint_daily_limit(client, seed_users, monkeypatch):
    users = seed_users()
    monkeypatch.setattr(settings, "complaint_rate_limit_10min", 100)
    for index in range(20):
        response = _submit(client, users, index=index)
        assert response.status_code == 201, response.text
    response = _submit(client, users, index=21)
    assert response.status_code == 429
    assert "Daily reporting limit" in response.json()["detail"]


def test_signup_limited_to_10_per_hour_per_ip(client, db, monkeypatch):
    monkeypatch.setattr(security, "create_supabase_auth_user", lambda *_args: {"id": "11111111-1111-1111-1111-111111111111"})
    for index in range(10):
        response = client.post("/auth/student/signup", json={
            "name": "Student", "email": f"student{index}@example.test", "password": "long-password",
        })
        assert response.status_code == 201, response.text

    response = client.post("/auth/student/signup", json={
        "name": "Student", "email": "student11@example.test", "password": "long-password",
    })
    assert response.status_code == 429
    assert "Too many sign-up attempts" in response.json()["detail"]


def test_client_ip_prefers_forwarded_for_first_hop():
    from types import SimpleNamespace

    request = SimpleNamespace(headers={"x-forwarded-for": "203.0.113.7, 10.0.0.2"}, client=SimpleNamespace(host="127.0.0.1"))
    assert rate_limit.client_ip(request) == "203.0.113.7"

    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="192.168.1.9"))
    assert rate_limit.client_ip(request) == "192.168.1.9"
