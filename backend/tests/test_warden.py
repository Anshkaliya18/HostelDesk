"""Warden dashboard, directory, and queue filtering authorization tests."""

from app.db.models import ComplaintCategory, ComplaintStatus, Severity, User
from tests.conftest import auth_header


def test_warden_dashboard_and_worker_directory(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    create_complaint(student=student, severity=Severity.HIGH)

    dashboard = client.get("/warden/dashboard", headers=auth_header(users["warden"]))
    assert dashboard.status_code == 200
    assert dashboard.json()["total"] == 1
    assert dashboard.json()["pending"] == 1
    assert dashboard.json()["high_priority"] == 1
    assert len(dashboard.json()["workers"]) == 2

    workers = client.get("/warden/workers", headers=auth_header(users["warden"]))
    assert workers.status_code == 200
    assert {worker["worker_type"] for worker in workers.json()} == {"ELECTRICIAN", "PLUMBER"}


def test_warden_queue_search_and_filters(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    create_complaint(student=student, block="A", category=ComplaintCategory.ELECTRICAL)
    create_complaint(student=student, block="B", category=ComplaintCategory.PLUMBING,
                     status=ComplaintStatus.ASSIGNED, severity=Severity.HIGH)

    response = client.get("/complaints?category=PLUMBING&status=ASSIGNED&search=Student%20One",
                          headers=auth_header(users["warden"]))
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["block"] == "B"


def test_warden_only_endpoints_reject_student_and_worker(client, seed_users):
    users = seed_users()
    for user_id in (users["student"], users["worker_electrician_user"]):
        assert client.get("/warden/dashboard", headers=auth_header(user_id)).status_code == 403
        assert client.get("/warden/workers", headers=auth_header(user_id)).status_code == 403
        assert client.get("/warden/reports", headers=auth_header(user_id)).status_code == 403
