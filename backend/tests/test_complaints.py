"""Critical business-rule tests for the HostelDesk complaint lifecycle."""

from tests.conftest import jpeg_bytes, auth_header


# ---- 1. Health endpoint ------------------------------------------------------


def test_health_and_root(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "connected"}

    root = client.get("/")
    assert root.status_code == 200
    assert "HostelDesk" in root.json()["message"]


# ---- 2. Complaint creation validation ----------------------------------------


def test_create_complaint_happy_path_with_photo(client, seed_users):
    users = seed_users()
    response = client.post(
        "/complaints",
        data={
            "description": "Ceiling fan sparking loudly in room 204 since Monday morning.",
            "block": "A",
            "room": "204",
        },
        files={"photo": ("fan.jpg", jpeg_bytes(), "image/jpeg")},
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # The response is FAST: complaint saved and returned before AI completes.
    assert body["status"] == "SUBMITTED"
    assert body["block"] == "A"
    assert body["photo_available"] is True
    assert body["history"], "initial SUBMITTED history should already exist"
    assert body["ai_recommendation"] is None  # AI still running in background


def test_create_complaint_requires_fields(client, seed_users):
    users = seed_users()
    response = client.post(
        "/complaints",
        data={"description": "", "block": "", "room": ""},
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 422


def test_create_complaint_short_description_rejected(client, seed_users):
    users = seed_users()
    response = client.post(
        "/complaints",
        data={"description": "short", "block": "A", "room": "204"},
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 422


def test_create_complaint_rejects_corrupt_photo(client, seed_users):
    users = seed_users()
    response = client.post(
        "/complaints",
        data={
            "description": "Tap leaking, please check the wash basin urgently.",
            "block": "C",
            "room": "112",
        },
        files={"photo": ("evil.jpg", b"not really an image", "image/jpeg")},
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 400
    assert "JPEG" in response.json()["detail"] or "Photo" in response.json()["detail"]


def test_create_complaint_unknown_user_rejected(client):
    response = client.post(
        "/complaints",
        data={
            "description": "Someone without a user id cannot submit.",
            "block": "A",
            "room": "204",
        },
    )
    assert response.status_code == 401


# ---- 3. Student ownership ----------------------------------------------------


def test_student_sees_only_own_complaint(client, seed_users, create_complaint, db):
    users = seed_users()
    from app.db.models import User

    other_student = db.get(User, users["student"])
    mine = create_complaint(student=other_student)
    response = client.get(f"/complaints/{mine.id}", headers=auth_header(users["student"]))
    assert response.status_code == 200
    assert response.json()["id"] == mine.id


def test_student_cannot_see_other_students_complaint(client, seed_users, create_complaint, db):
    users = seed_users()
    from app.db.models import User

    other = db.get(User, users["student"])
    complaint = create_complaint(student=other)
    response = client.get(f"/complaints/{complaint.id}", headers=auth_header(users["worker_electrician_user"]))
    assert response.status_code == 404


# ---- 4. Warden access --------------------------------------------------------


def test_warden_queue_lists_all_complaints(client, seed_users, create_complaint, db):
    users = seed_users()
    from app.db.models import User

    student = db.get(User, users["student"])
    complaint = create_complaint(student=student)

    queue = client.get("/complaints", headers=auth_header(users["warden"]))
    assert queue.status_code == 200
    ids = [item["id"] for item in queue.json()]
    assert complaint.id in ids
    assert users["student"] == queue.json()[0]["student"]["id"]


def test_student_cannot_access_warden_queue(client, seed_users):
    users = seed_users()
    response = client.get("/complaints", headers=auth_header(users["student"]))
    assert response.status_code == 403


def test_worker_cannot_access_warden_queue(client, seed_users):
    users = seed_users()
    response = client.get("/complaints", headers=auth_header(users["worker_electrician_user"]))
    assert response.status_code == 403


def test_missing_auth_returns_401(client):
    assert client.get("/complaints").status_code == 401
