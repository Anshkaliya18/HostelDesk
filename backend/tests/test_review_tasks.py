"""Warden review gate + worker task ownership/completion tests."""

from app.db.models import ComplaintStatus, Task, TaskStatus
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


# ---- 5. Warden review ---------------------------------------------------------


def test_warden_review_assigns_worker_and_creates_task(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)

    review = client.patch(
        f"/complaints/{complaint['id']}/review",
        json={"category": "ELECTRICAL", "severity": "HIGH", "worker_id": users["electrician"], "warden_note": "Needs urgent repair"},
        headers=auth_header(users["warden"]),
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["status"] == "ASSIGNED"
    assert body["category"] == "ELECTRICAL"
    assert body["approved_worker"]["id"] == users["electrician"]
    assert body["ai_recommendation"]["raw_response"] is not None

    task = db.query(Task).filter(Task.complaint_id == complaint["id"]).one()
    assert task.status == TaskStatus.ASSIGNED
    assert task.worker_id == users["electrician"]


def test_second_review_is_rejected(client, seed_users):
    users = seed_users()
    complaint = _submit(client, users)
    review_url = f"/complaints/{complaint['id']}/review"
    payload = {"category": "ELECTRICAL", "severity": "HIGH", "worker_id": users["electrician"]}
    first = client.patch(review_url, json=payload, headers=auth_header(users["warden"]))
    assert first.status_code == 200

    second = client.patch(review_url, json=payload, headers=auth_header(users["warden"]))
    assert second.status_code == 409


def test_warden_review_rejects_unknown_worker(client, seed_users):
    users = seed_users()
    complaint = _submit(client, users)
    response = client.patch(
        f"/complaints/{complaint['id']}/review",
        json={"category": "ELECTRICAL", "severity": "HIGH", "worker_id": 9999},
        headers=auth_header(users["warden"]),
    )
    assert response.status_code == 404


def test_worker_cannot_review_complaints(client, seed_users):
    users = seed_users()
    complaint = _submit(client, users)
    response = client.patch(
        f"/complaints/{complaint['id']}/review",
        json={"category": "ELECTRICAL", "severity": "HIGH", "worker_id": users["electrician"]},
        headers=auth_header(users["worker_electrician_user"]),
    )
    assert response.status_code == 403


# ---- 6. Worker task ownership --------------------------------------------------


def _assign(client, users, complaint_id, worker_id):
    response = client.patch(
        f"/complaints/{complaint_id}/review",
        json={"category": "ELECTRICAL", "severity": "HIGH", "worker_id": worker_id},
        headers=auth_header(users["warden"]),
    )
    assert response.status_code == 200
    return response.json()


def test_worker_sees_only_their_tasks(client, seed_users, db):
    users = seed_users()
    first = _submit(client, users)
    second = _submit(client, users)
    _assign(client, users, first["id"], users["electrician"])
    _assign(client, users, second["id"], users["plumber"])

    own = client.get("/tasks/my", headers=auth_header(users["worker_electrician_user"]))
    assert own.status_code == 200
    ids = [task["id"] for task in own.json()]
    first_task = db.query(Task).filter(Task.complaint_id == first["id"]).one().id
    second_task = db.query(Task).filter(Task.complaint_id == second["id"]).one().id
    assert ids == [first_task]

    plumber_tasks = client.get("/tasks/my", headers=auth_header(users["worker_plumber_user"])).json()
    assert [task["id"] for task in plumber_tasks] == [second_task]


def test_worker_cannot_update_someone_elses_task(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _assign(client, users, complaint["id"], users["electrician"])

    task = db.query(Task).filter(Task.complaint_id == complaint["id"]).one()
    response = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_header(users["worker_plumber_user"]),
    )
    assert response.status_code == 404


# ---- 7. Worker completion transition -------------------------------------------


def test_worker_cannot_complete_without_starting(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _assign(client, users, complaint["id"], users["electrician"])
    task = db.query(Task).filter(Task.complaint_id == complaint["id"]).one()

    illegal = client.patch(
        f"/tasks/{task.id}/status", json={"status": "COMPLETED"}, headers=auth_header(users["worker_electrician_user"])
    )
    assert illegal.status_code == 400


def test_full_worker_lifecycle_completes_complaint(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    _assign(client, users, complaint["id"], users["electrician"])
    task = db.query(Task).filter(Task.complaint_id == complaint["id"]).one()

    start = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "IN_PROGRESS", "note": "started repair"},
        headers=auth_header(users["worker_electrician_user"]),
    )
    assert start.status_code == 200
    assert start.json()["status"] == "IN_PROGRESS"

    finish = client.patch(
        f"/tasks/{task.id}/status",
        json={"status": "COMPLETED", "note": "Replaced the wall socket."},
        headers=auth_header(users["worker_electrician_user"]),
    )
    assert finish.status_code == 200
    assert finish.json()["status"] == "COMPLETED"
    assert finish.json()["note"] == "Replaced the wall socket."

    db.expire_all()
    from app.db.models import Complaint

    complaint_row = db.get(Complaint, complaint["id"])
    assert complaint_row.status == ComplaintStatus.COMPLETED
    assert complaint_row.completed_at is not None
    assert complaint_row.worker_note == "Replaced the wall socket."

    detail = client.get(f"/complaints/{complaint['id']}", headers=auth_header(users["student"]))
    assert detail.status_code == 200
    assert detail.json()["status"] == "COMPLETED"
