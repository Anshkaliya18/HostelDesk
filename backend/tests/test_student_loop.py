"""Student confirmation/reopen loop on completed complaints (Phase 2c)."""

import uuid

from app.db.models import Complaint, StatusHistory, Task, User, UserRole
from tests.conftest import auth_header


def _submit(client, users):
    response = client.post(
        "/complaints",
        data={
            "description": "Power socket in C block room 112 is completely dead.",
            "block": "C",
            "room": "112",
        },
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reach_completed(client, users, db, complaint):
    review = client.patch(
        f"/complaints/{complaint['id']}/review",
        json={"category": "ELECTRICAL", "severity": "HIGH", "worker_id": users["electrician"]},
        headers=auth_header(users["warden"]),
    )
    assert review.status_code == 200, review.text
    task = db.query(Task).filter_by(complaint_id=complaint["id"]).one()
    start = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "IN_PROGRESS", "note": "started repair"},
        headers=auth_header(users["worker_electrician_user"]),
    )
    assert start.status_code == 200
    finish = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "COMPLETED", "note": "Replaced the damaged wall socket."},
        headers=auth_header(users["worker_electrician_user"]),
    )
    assert finish.status_code == 200


def _second_student(db):
    student = User(name="Student Two", role=UserRole.STUDENT, block="B", room="202")
    db.add(student)
    db.flush()
    student.auth_user_id = uuid.UUID(int=student.id)
    db.commit()
    return student


def test_student_confirms_completed_complaint(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _reach_completed(client, users, db, complaint)

    confirm = client.post(
        f"/complaints/{complaint['id']}/confirm", headers=auth_header(users["student"])
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["status"] == "COMPLETED"
    notes = [entry["note"] for entry in body["history"]]
    assert "Student confirmed resolved" in notes


def test_double_confirm_is_rejected(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _reach_completed(client, users, db, complaint)
    first = client.post(f"/complaints/{complaint['id']}/confirm", headers=auth_header(users["student"]))
    assert first.status_code == 200
    second = client.post(f"/complaints/{complaint['id']}/confirm", headers=auth_header(users["student"]))
    assert second.status_code == 409


def test_confirm_requires_owner_only(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _reach_completed(client, users, db, complaint)

    wrong_student = _second_student(db)
    owner_only = client.post(
        f"/complaints/{complaint['id']}/confirm", headers=auth_header(wrong_student.id)
    )
    assert owner_only.status_code == 404
    # Non-students get 403 from the role gate.
    warden_attempt = client.post(
        f"/complaints/{complaint['id']}/confirm", headers=auth_header(users["warden"])
    )
    assert warden_attempt.status_code == 403


def test_confirm_requires_completed_status(client, seed_users):
    users = seed_users()
    complaint = _submit(client, users)
    early = client.post(f"/complaints/{complaint['id']}/confirm", headers=auth_header(users["student"]))
    assert early.status_code == 409


def test_student_reopens_completed_complaint(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _reach_completed(client, users, db, complaint)

    reopen = client.post(
        f"/complaints/{complaint['id']}/reopen",
        json={"reason": "The fan started sparking again after one day."},
        headers=auth_header(users["student"]),
    )
    assert reopen.status_code == 200, reopen.text
    body = reopen.json()
    assert body["status"] == "WARDEN_REVIEW"
    assert body["completed_at"] is None
    reopen_note = body["history"][-1]["note"]
    assert reopen_note.startswith("Reopened by student:")
    assert "sparking again" in reopen_note


def test_reopen_lets_warden_reassign(client, seed_users, db):
    from app.db.models import Task

    users = seed_users()
    complaint = _submit(client, users)
    _reach_completed(client, users, db, complaint)
    reopen = client.post(
        f"/complaints/{complaint['id']}/reopen",
        json={"reason": "The socket is loose again and sparks occasionally."},
        headers=auth_header(users["student"]),
    )
    assert reopen.status_code == 200

    review = client.patch(
        f"/complaints/{complaint['id']}/review",
        json={"category": "ELECTRICAL", "severity": "MEDIUM", "worker_id": users["electrician"]},
        headers=auth_header(users["warden"]),
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "ASSIGNED"
    tasks = db.query(Task).filter_by(complaint_id=complaint["id"]).all()
    assert len(tasks) == 2
    assert tasks[-1].status.value == "ASSIGNED"


def test_reopen_validates_reason_and_status(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)

    # Reason too short.
    short = client.post(
        f"/complaints/{complaint['id']}/reopen",
        json={"reason": "bad"},
        headers=auth_header(users["student"]),
    )
    assert short.status_code == 422

    # Not completed yet.
    not_completed = client.post(
        f"/complaints/{complaint['id']}/reopen",
        json={"reason": "It is broken again and keeps sparking loudly."},
        headers=auth_header(users["student"]),
    )
    assert not_completed.status_code == 409


def test_complaints_mine_includes_assigned_worker_name(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _reach_completed(client, users, db, complaint)

    mine = client.get("/complaints/mine", headers=auth_header(users["student"]))
    assert mine.status_code == 200
    row = mine.json()[0]
    assert row["approved_worker"] is not None
    assert row["approved_worker"]["name"] == "Worker One"
    assert row["worker_note"] if "worker_note" in row else True
