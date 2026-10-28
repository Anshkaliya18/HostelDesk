"""Repeat-problem rule + daily digest tests."""

from app.db.models import User
from app.services import insights_service
from tests.conftest import auth_header


def test_no_alert_below_threshold(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    for complaint in (
        create_complaint(student=student, block="A"),
        create_complaint(student=student, block="A"),
    ):
        insights_service.evaluate_repeat_problem(db, complaint)

    alerts = client.get("/alerts", headers=auth_header(users["warden"]))
    assert alerts.status_code == 200
    assert alerts.json() == []


def test_repeat_problem_alert_at_three_complaints(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    for days_ago in (5, 3, 0):
        complaint = create_complaint(student=student, block="A", days_ago=days_ago)
        insights_service.evaluate_repeat_problem(db, complaint)

    alerts = client.get("/alerts", headers=auth_header(users["warden"]))
    assert alerts.status_code == 200
    payload = alerts.json()
    assert len(payload) == 1
    alert = payload[0]
    assert alert["block"] == "A"
    assert alert["category"] == "ELECTRICAL"
    assert alert["complaint_count"] == 3
    assert alert["alert_type"] == "REPEAT_PROBLEM"
    assert alert["resolved_at"] is None


def test_alert_count_refreshes_when_more_complaints_arrive(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    for days_ago in (4, 3, 2):
        complaint = create_complaint(student=student, block="A", days_ago=days_ago)
        insights_service.evaluate_repeat_problem(db, complaint)
    fourth = create_complaint(student=student, block="A")
    insights_service.evaluate_repeat_problem(db, fourth)

    alerts = client.get("/alerts", headers=auth_header(users["warden"])).json()
    assert len(alerts) == 1
    assert alerts[0]["complaint_count"] == 4


def test_old_complaints_outside_window_do_not_trigger(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    for days_ago in (25, 20, 15):
        complaint = create_complaint(student=student, block="B", days_ago=days_ago)
        insights_service.evaluate_repeat_problem(db, complaint)

    alerts = client.get("/alerts", headers=auth_header(users["warden"])).json()
    assert alerts == []


def test_student_cannot_view_alerts(client, seed_users):
    users = seed_users()
    response = client.get("/alerts", headers=auth_header(users["student"]))
    assert response.status_code == 403


# ---- Alert resolution lifecycle ---------------------------------------------


def _create_active_alert(client, db, users, create_complaint, student) -> int:
    """Three same-block complaints inside the window -> one active alert."""
    for days_ago in (5, 3, 0):
        complaint = create_complaint(student=student, block="A", days_ago=days_ago)
        insights_service.evaluate_repeat_problem(db, complaint)
    # Commit before any API call: request teardown rolls back the shared
    # test connection, which would discard flushed-but-uncommitted rows.
    db.commit()
    alerts = client.get("/alerts", headers=auth_header(users["warden"])).json()
    assert len(alerts) == 1
    return alerts[0]["id"]


def test_warden_resolves_alert_and_state_persists(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    alert_id = _create_active_alert(client, db, users, create_complaint, student)

    response = client.post(
        f"/alerts/{alert_id}/resolve", headers=auth_header(users["warden"])
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == alert_id
    assert body["resolved_at"] is not None

    # The active list no longer includes it...
    assert client.get("/alerts", headers=auth_header(users["warden"])).json() == []
    # ...and the resolved state persists across reloads.
    resolved = client.get(
        "/alerts", params={"status": "resolved"}, headers=auth_header(users["warden"])
    ).json()
    assert [alert["id"] for alert in resolved] == [alert_id]
    assert resolved[0]["resolved_at"] is not None


def test_students_and_workers_cannot_resolve_alerts(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    alert_id = _create_active_alert(client, db, users, create_complaint, student)

    for role in ("student", "worker_electrician_user"):
        response = client.post(
            f"/alerts/{alert_id}/resolve", headers=auth_header(users[role])
        )
        assert response.status_code == 403

    # The alert is untouched and still active.
    alerts = client.get("/alerts", headers=auth_header(users["warden"])).json()
    assert len(alerts) == 1
    assert alerts[0]["resolved_at"] is None


def test_resolve_unknown_alert_returns_404(client, seed_users):
    users = seed_users()
    response = client.post("/alerts/9999/resolve", headers=auth_header(users["warden"]))
    assert response.status_code == 404


def test_resolving_an_alert_twice_returns_409(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    alert_id = _create_active_alert(client, db, users, create_complaint, student)

    first = client.post(
        f"/alerts/{alert_id}/resolve", headers=auth_header(users["warden"])
    )
    assert first.status_code == 200
    second = client.post(
        f"/alerts/{alert_id}/resolve", headers=auth_header(users["warden"])
    )
    assert second.status_code == 409


def test_recurrence_after_resolution_creates_a_new_alert(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    alert_id = _create_active_alert(client, db, users, create_complaint, student)
    client.post(f"/alerts/{alert_id}/resolve", headers=auth_header(users["warden"]))

    # The problem recurs after the warden resolved the old alert: the new
    # evaluation must not be swallowed by the resolved alert.
    fourth = create_complaint(student=student, block="A")
    insights_service.evaluate_repeat_problem(db, fourth)
    db.commit()

    active = client.get("/alerts", headers=auth_header(users["warden"])).json()
    assert len(active) == 1
    new_alert = active[0]
    assert new_alert["id"] != alert_id
    assert new_alert["resolved_at"] is None
    assert new_alert["complaint_count"] == 4

    resolved = client.get(
        "/alerts", params={"status": "resolved"}, headers=auth_header(users["warden"])
    ).json()
    assert [alert["id"] for alert in resolved] == [alert_id]


# ---- Digest -----------------------------------------------------------------


def test_digest_counts_and_open_complaints(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    create_complaint(student=student, block="A")
    create_complaint(student=student, block="A")
    create_complaint(student=student, block="C")

    digest = client.get("/digest", headers=auth_header(users["warden"]))
    assert digest.status_code == 200
    body = digest.json()
    assert body["category_counts"]["ELECTRICAL"] == 3
    assert body["open_complaints"] == 3
    assert body["overdue_complaints"] == 0
    assert body["completed_complaints"] == 0


def test_worker_cannot_view_digest(client, seed_users):
    users = seed_users()
    response = client.get("/digest", headers=auth_header(users["worker_electrician_user"]))
    assert response.status_code == 403
