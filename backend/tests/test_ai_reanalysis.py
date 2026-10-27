"""Warden-triggered AI re-analysis and the bounded stale-complaint sweep."""

from app.db.models import User
from app.services import ai_service
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


def test_reanalyze_requires_warden_role(client, seed_users):
    users = seed_users()
    complaint = _submit(client, users)

    student = client.post(f"/complaints/{complaint['id']}/reanalyze", headers=auth_header(users["student"]))
    assert student.status_code == 403


def test_reanalyze_succeeds_after_failed_first_pass(client, seed_users, db, monkeypatch):
    """A failed first pass stores an error recommendation; the warden re-run
    must bypass that guard and produce a real classification."""
    users = seed_users()
    complaint = _submit(client, users)
    failed = client.get(f"/complaints/{complaint['id']}", headers=auth_header(users["student"]))
    assert failed.json()["ai_recommendation"]["raw_response"].get("error")

    calls = []

    async def better_model(image, mime, text, recent=None):
        calls.append(1)
        from app.schemas.ai import AIAnalysisResult

        return AIAnalysisResult.model_validate({
            "category": "ELECTRICAL",
            "severity": "HIGH",
            "suggested_worker": "ELECTRICIAN",
            "reason": "Dead socket in wall",
            "confidence": "HIGH",
            "model": "gemini-2.5-flash",
        })

    monkeypatch.setattr(ai_service, "analyze_complaint", better_model)
    response = client.post(f"/complaints/{complaint['id']}/reanalyze", headers=auth_header(users["warden"]))
    assert response.status_code == 200, response.text

    detail = client.get(f"/complaints/{complaint['id']}", headers=auth_header(users["warden"])).json()
    assert detail["category"] == "ELECTRICAL"
    assert detail["severity"] == "HIGH"
    assert detail["ai_recommendation"]["reason"] == "Dead socket in wall"
    assert len(calls) == 1


def test_reanalyze_rejected_once_assigned(client, seed_users, db):
    users = seed_users()
    complaint = _submit(client, users)
    client.patch(
        f"/complaints/{complaint['id']}/review",
        json={"category": "ELECTRICAL", "severity": "HIGH", "worker_id": users["electrician"]},
        headers=auth_header(users["warden"]),
    )
    response = client.post(f"/complaints/{complaint['id']}/reanalyze", headers=auth_header(users["warden"]))
    assert response.status_code == 409


def test_sweep_schedules_only_stale_submitted(client, seed_users, create_complaint, db, monkeypatch):
    users = seed_users()
    student = db.get(User, users["student"])

    stale = create_complaint(student, status=_status("SUBMITTED"), days_ago=1)
    stale_no_category = create_complaint(student, status=_status("SUBMITTED"), days_ago=1, severity=None, block="B")
    scheduled_calls = []

    async def fake_process(complaint_id, image, mime):
        scheduled_calls.append(complaint_id)

    monkeypatch.setattr(_complaint_service(), "process_complaint_ai", fake_process)
    response = client.post("/warden/ai-sweep", headers=auth_header(users["warden"]))
    assert response.status_code == 200, response.text

    ids = response.json()["scheduled"]
    stale_ids = {stale.id, stale_no_category.id}
    assert set(ids) <= stale_ids
    assert stale.id in ids  # the unclassifiable one is still swept (no recommendation yet)
    assert stale_no_category.id in ids
    assert sorted(scheduled_calls) == sorted(ids)  # TestClient runs the background sweep


def test_sweep_requires_warden(client, seed_users):
    users = seed_users()
    response = client.post("/warden/ai-sweep", headers=auth_header(users["student"]))
    assert response.status_code == 403


def _status(value):
    from app.db.models import ComplaintStatus

    return ComplaintStatus[value]


def _complaint_service():
    from app.services import complaint_service

    return complaint_service
