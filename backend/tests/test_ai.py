"""AI orchestration safety tests: invalid Gemini output must never crash
the complaint flow or assign a worker automatically."""

import asyncio
import json

import httpx
from app.services import ai_service, complaint_service
from tests.conftest import auth_header


class _StubResponse:
    """Minimal stand-in for httpx.Response used by ai_service."""

    def __init__(self, status_code: int, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self) -> dict:
        return self._body


class _FakeAsyncClient:
    """Fake httpx.AsyncClient that serves canned responses from a queue."""

    def __init__(self, queue: list[tuple[int, dict | None]]) -> None:
        self.queue = list(queue)
        self.calls: list[list] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def post(self, url: str, **kwargs: object) -> _StubResponse:
        self.calls.append([url, kwargs])
        if not self.queue:
            raise AssertionError("unexpected extra HTTP request (duplicate AI request)")
        status, body = self.queue.pop(0)
        return _StubResponse(status, body)


def _ok_body(text: str = '{"ok": true}') -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ]
    }


def _submit(client, users):
    response = client.post(
        "/complaints",
        data={
            "description": "Water cooler in the mess hall is leaking badly.",
            "block": "B",
            "room": "201",
        },
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _detail(client, users, complaint_id: int) -> dict:
    """Fetch the complaint after the background AI task has run."""
    response = client.get(
        f"/complaints/{complaint_id}", headers=auth_header(users["student"])
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_missing_api_key_keeps_complaint_in_warden_review(client, seed_users):
    users = seed_users()
    body = _submit(client, users)
    # Fast response: the complaint is returned BEFORE the AI finishes/fails.
    assert body["status"] == "SUBMITTED"
    assert body["ai_recommendation"] is None

    detail = _detail(client, users, body["id"])
    assert detail["status"] == "WARDEN_REVIEW"
    assert detail["category"] is None
    assert detail["ai_suggested_worker"] is None
    assert detail["ai_recommendation"] is not None
    assert "error" in detail["ai_recommendation"]["raw_response"]


def test_unexpected_gemini_payload_becomes_safe_failure(client, seed_users, monkeypatch):
    users = seed_users()

    async def fake(*args, **kwargs):
        return {"nonsense": True}

    monkeypatch.setattr(ai_service, "_call_gemini_async", fake)
    body = _submit(client, users)
    assert body["status"] == "SUBMITTED"

    detail = _detail(client, users, body["id"])
    assert detail["status"] == "WARDEN_REVIEW"
    recommendation = detail["ai_recommendation"]
    assert recommendation["category"] is None
    assert recommendation["severity"] is None
    assert recommendation["suggested_worker"] is None
    assert "error" in recommendation["raw_response"]


def test_gemini_invalid_enum_value_is_rejected(client, seed_users, monkeypatch):
    users = seed_users()

    async def fake(*args, **kwargs):
        return {
            "category": "SPACESHIP",
            "severity": "HIGH",
            "suggested_worker": "ELECTRICIAN",
        }

    monkeypatch.setattr(ai_service, "_call_gemini_async", fake)
    body = _submit(client, users)
    assert body["status"] == "SUBMITTED"

    detail = _detail(client, users, body["id"])
    assert detail["category"] is None
    assert "error" in detail["ai_recommendation"]["raw_response"]
    # AI failure must not pre-fill the suggestion either.
    assert detail["ai_suggested_worker"] is None


def test_valid_gemini_json_is_normalized_and_stored(client, seed_users, monkeypatch):
    users = seed_users()

    async def fake(*args, **kwargs):
        return {
            "category": "electrical",
            "severity": " HIGH ",
            "suggested_worker": "Electrician",
        }

    monkeypatch.setattr(ai_service, "_call_gemini_async", fake)
    body = _submit(client, users)
    assert body["status"] == "SUBMITTED"

    detail = _detail(client, users, body["id"])
    assert detail["status"] == "WARDEN_REVIEW"
    assert detail["category"] == "ELECTRICAL"
    assert detail["severity"] == "HIGH"
    assert detail["ai_suggested_worker"] == "ELECTRICIAN"
    assert detail["ai_recommendation"]["raw_response"] == {
        "category": "ELECTRICAL",
        "severity": "HIGH",
        "suggested_worker": "ELECTRICIAN",
    }


def test_gemini_transport_error_returns_safe_failure(client, seed_users, monkeypatch):
    users = seed_users()

    class _RaisingAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("network down")

    # Force the API key check to pass so the HTTP layer is really exercised.
    monkeypatch.setattr(ai_service.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", _RaisingAsyncClient)
    body = _submit(client, users)
    assert body["status"] == "SUBMITTED"

    detail = _detail(client, users, body["id"])
    assert detail["status"] == "WARDEN_REVIEW"
    assert "error" in detail["ai_recommendation"]["raw_response"]


def test_unexpected_ai_crash_keeps_persisted_complaint(client, seed_users, monkeypatch):
    """A crash during the AI phase must not erase the already-committed row."""
    users = seed_users()

    async def blow_up(*args, **kwargs):
        raise RuntimeError("simulated Gemma crash mid-request")

    monkeypatch.setattr(ai_service, "analyze_complaint", blow_up)
    response = client.post(
        "/complaints",
        data={"description": "Ceiling fan sparks when I turn it on.", "block": "C", "room": "105"},
        headers=auth_header(users["student"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # Complaint survives, no automatic worker, warden can act on it manually.
    assert body["id"] is not None
    assert body["status"] == "SUBMITTED"

    detail = _detail(client, users, body["id"])
    assert detail["status"] == "WARDEN_REVIEW"
    # No automatic worker, no fake AI data recorded.
    assert detail["ai_suggested_worker"] is None
    assert detail["category"] is None
    assert detail["ai_recommendation"] is None  # nothing fabricated on a crash


def test_background_ai_runs_exactly_once_per_complaint(client, seed_users, monkeypatch):
    """Double submission/duplicate scheduling must not call Gemma twice."""
    users = seed_users()
    calls: list[int] = []

    async def counting_gemini(*args, **kwargs):
        calls.append(1)
        return {"category": "CLEANING", "severity": "LOW", "suggested_worker": "CLEANER"}

    monkeypatch.setattr(ai_service, "_call_gemini_async", counting_gemini)
    body = _submit(client, users)
    assert len(calls) == 1

    # A second scheduled run (e.g. double-click, retried task) is a no-op.
    asyncio.run(complaint_service.process_complaint_ai(body["id"], None, None))
    assert len(calls) == 1

    detail = _detail(client, users, body["id"])
    assert detail["status"] == "WARDEN_REVIEW"
    assert detail["category"] == "CLEANING"


def test_warden_review_during_ai_run_is_preserved(client, seed_users, db, monkeypatch):
    """AI must never overwrite the status the warden already moved forward."""
    from app.db.database import SessionLocal
    from app.db.models import Complaint, User
    from app.services import task_service
    from app.schemas.complaint import ReviewRequest

    users = seed_users()
    description = "Water cooler in the mess hall is leaking badly."

    async def review_then_analyze(image, mime, text):
        # The warden acts WHILE the (stubbed) AI call is in flight.
        review_db = SessionLocal()
        try:
            complaint = review_db.query(Complaint).filter_by(description=description).one()
            warden = review_db.get(User, users["warden"])
            task_service.review_complaint(
                review_db,
                warden,
                complaint.id,
                ReviewRequest(
                    category="ELECTRICAL",
                    severity="HIGH",
                    worker_id=users["electrician"],
                    warden_note="Warden decided first",
                ),
            )
            review_db.commit()
        finally:
            review_db.close()
        return {"category": "PLUMBING", "severity": "LOW", "suggested_worker": "PLUMBER"}

    monkeypatch.setattr(ai_service, "_call_gemini_async", review_then_analyze)
    body = _submit(client, users)

    detail = _detail(client, users, body["id"])
    # Warden's decision stands: ASSIGNED, not overwritten by background AI.
    assert detail["status"] == "ASSIGNED"
    assert detail["approved_worker"]["id"] == users["electrician"]
    # The recommendation is still recorded (AI suggests), but never auto-applied.
    assert detail["ai_recommendation"]["raw_response"] == {
        "category": "PLUMBING",
        "severity": "LOW",
        "suggested_worker": "PLUMBER",
    }
    assert detail["category"] == "ELECTRICAL"  # warden's final category wins


# ---------------------------------------------------------------------------
# Model chain: primary gemma-4-31b-it with fallback gemma-4-26b-a4b-it,
# bounded retries for transient failures, never a duplicate/rogue request.
# Tight policy: 1 attempt + 1 retry per model, then fallback once.
# Max 4 total Gemini requests per complaint.
# ---------------------------------------------------------------------------


def _chain(monkeypatch, responses):
    """Patch httpx.AsyncClient to serve canned responses in order; record model names."""
    fake_client = _FakeAsyncClient(responses)
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda: fake_client)

    async def _noop_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(ai_service.asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(ai_service.settings, "gemini_api_key", "test-key")
    return fake_client.calls


def test_thinking_model_answer_part_is_used_not_the_thought():
    """Gemma 4 thinking models emit 'thought' parts first; the answer is last."""
    parts = [
        {"thought": True, "text": "reasoning about the fan..."},
        {"thought": True, "text": "more reasoning..."},
        {"text": '{"category": "ELECTRICAL"}'},
    ]
    assert ai_service._extract_answer_text(parts) == '{"category": "ELECTRICAL"}'
    assert ai_service._extract_answer_text([{"text": '{"plain": 1}'}]) == '{"plain": 1}'
    assert ai_service._extract_answer_text([{"thought": True, "text": "only thoughts"}]) is None


def test_primary_503_exhausts_bounded_retries_falls_back_and_succeeds(monkeypatch):
    calls = _chain(
        monkeypatch,
        [
            (503, {"error": {"message": "Service unavailable"}}),
            (503, {"error": {"message": "Service unavailable"}}),
            (200, _ok_body()),
        ],
    )
    result = asyncio.run(ai_service._call_gemini_async(None, None, "fan broken"))
    # 31b: 1 attempt + 1 bounded retry, then 26b-a4b succeeded on its first try.
    models = [call[0].split("/models/")[-1].split(":")[0] for call in calls]
    assert models == ["gemma-4-31b-it", "gemma-4-31b-it", "gemma-4-26b-a4b-it"]
    assert result["model"] == "gemma-4-26b-a4b-it"


def test_429_then_success_never_hits_fallback(monkeypatch):
    calls = _chain(
        monkeypatch,
        [
            (429, {"error": {"message": "rate limit exceeded"}}),
            (200, _ok_body()),
        ],
    )
    result = asyncio.run(ai_service._call_gemini_async(None, None, "fan broken"))
    assert len(calls) == 2  # exactly one retry, no fallback request
    assert result["model"] == "gemma-4-31b-it"


def test_4xx_not_retried_moves_straight_to_fallback(monkeypatch):
    calls = _chain(
        monkeypatch,
        [
            (404, {"error": {"message": "model not found"}}),
            (200, _ok_body()),
        ],
    )
    result = asyncio.run(ai_service._call_gemini_async(None, None, "fan broken"))
    models = [call[0].split("/models/")[-1].split(":")[0] for call in calls]
    assert models == ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]
    assert len(calls) == 2  # one 4xx on primary + one success on fallback


def test_exhausted_retries_and_fallback_fail_cleanly(monkeypatch):
    calls = _chain(
        monkeypatch,
        [
            (429, {"error": {"message": "rate limit exceeded"}}),
            (429, {"error": {"message": "rate limit exceeded"}}),
            (429, {"error": {"message": "rate limit exceeded"}}),
            (429, {"error": {"message": "rate limit exceeded"}}),
        ],
    )
    result = asyncio.run(ai_service._call_gemini_async(None, None, "fan broken"))
    # Deterministic, controlled failure - never a fabricated analysis.
    assert result["error"] == "gemini_unavailable"
    assert len(calls) == 4  # 2 per model (1 attempt + 1 retry) - and no more


def test_all_models_gone_returns_unavailable_not_fake_data(monkeypatch):
    calls = _chain(
        monkeypatch,
        [
            (500, {"error": {"message": "Internal error encountered."}}),
            (500, {"error": {"message": "Internal error encountered."}}),
        ],
    )
    result = asyncio.run(ai_service._call_gemini_async(None, None, "fan broken"))
    assert result["error"] == "gemini_unavailable"
    # 500 is non-retryable: 1 call per model, then done.
    assert len(calls) == 2


def test_markdown_fenced_answer_is_parsed(monkeypatch):
    _chain(
        monkeypatch,
        [
            (200, _ok_body('```json\n{"category": "PLUMBING"}\n```')),
        ],
    )
    result = asyncio.run(ai_service._call_gemini_async(None, None, "tap leaking"))
    assert result["category"] == "PLUMBING"
