"""Warden queue filters: block normalization, needs-review, oldest-unreviewed."""

from app.db.models import User
from tests.conftest import auth_header


def test_queue_filters_by_block_normalized(client, seed_users, create_complaint, db):
    users = seed_users()
    student = db.get(User, users["student"])
    blocker = create_complaint(student, block="B")
    create_complaint(student, block="A", status=__import__("app.db.models", fromlist=["ComplaintStatus"]).ComplaintStatus.SUBMITTED)

    response = client.get("/complaints", params={"block": " block b "}, headers=auth_header(users["warden"]))
    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()]
    assert ids == [blocker.id]


def test_needs_review_expands_unreviewed_status(client, seed_users, create_complaint, db):
    from app.db.models import ComplaintStatus

    users = seed_users()
    student = db.get(User, users["student"])
    submitted = create_complaint(student, status=ComplaintStatus.SUBMITTED)
    review = create_complaint(student, status=ComplaintStatus.WARDEN_REVIEW, block="C")
    done = create_complaint(student, status=ComplaintStatus.COMPLETED, block="D")

    response = client.get("/complaints", params={"needs_review": "true"}, headers=auth_header(users["warden"]))
    ids = {row["id"] for row in response.json()}
    assert submitted.id in ids and review.id in ids and done.id not in ids


def test_sort_review_pairs_with_needs_review(client, seed_users, create_complaint, db):
    from app.db.models import ComplaintStatus

    users = seed_users()
    student = db.get(User, users["student"])
    older = create_complaint(student, status=ComplaintStatus.SUBMITTED, days_ago=3, block="B")
    newer = create_complaint(student, status=ComplaintStatus.WARDEN_REVIEW, block="D")

    response = client.get(
        "/complaints", params={"needs_review": "true", "sort": "review"},
        headers=auth_header(users["warden"]),
    )
    ids = [row["id"] for row in response.json()]
    assert ids == [older.id, newer.id]  # oldest unreviewed first
