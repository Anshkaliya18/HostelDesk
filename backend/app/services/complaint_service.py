"""Complaint service: creation + AI analysis, role-scoped reads."""

import logging
import time
from collections.abc import Callable
from datetime import timedelta

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AIRecommendation,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Severity,
    StatusHistory,
    User,
    UserRole,
    Worker,
    WorkerType,
    utcnow,
)
from app.schemas.ai import AIAnalysisResult
from app.services import ai_service
from app.utils.normalize import normalize_block
from app.utils.storage import StorageUnavailableError, get_image_storage, validate_upload_or_400

logger = logging.getLogger(__name__)

_CONFIRMED_NOTE = "Student confirmed resolved"


def _system_write(
    db: Session,
    action,
):
    """Run a trusted server-side write in one SYSTEM-context transaction.

    Students have no complaints UPDATE policy and a status_history INSERT
    policy limited to first submissions, so confirm/reopen perform their
    validated write under the SYSTEM context (owner checks happen before this
    wrapper on the request context), then restore the request context.
    """
    from app.db.database import set_database_security_context  # noqa: F401 - mirrors get_db pattern

    request_context = dict(db.info.get("hosteldesk_security_context") or {})
    set_database_security_context(db, "SYSTEM")
    try:
        return action()
    finally:
        db.info["hosteldesk_security_context"] = request_context


def _add_history(
    db: Session,
    complaint: Complaint,
    old_status: ComplaintStatus | None,
    new_status: ComplaintStatus,
    actor: User | None,
    note: str | None = None,
) -> None:
    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=actor.id if actor else None,
            note=note,
        )
    )


def create_complaint(
    db: Session,
    student: User,
    description: str,
    block: str,
    room: str,
    photo: UploadFile | None,
) -> tuple[Complaint, bytes | None, str | None]:
    """FAST PATH: persist the complaint (+ photo) and return immediately.

    Ordering (failures in later steps must never erase the complaint):
      1. validate the optional photo (reads bytes once; handed off to the
         background task afterwards, so the file is never read twice)
      2. insert complaint (SUBMITTED) + first status_history row -> COMMIT
      3. upload the private photo -> COMMIT (failure keeps the complaint,
         records a recoverable state, and surfaces HTTP 503)
      4. RETURN - the caller schedules ``process_complaint_ai`` as background
         work, so the student never waits for Gemini (20-80s) in the request.

    Returns ``(complaint, image_bytes, image_mime)`` for the background task.
    """
    started = time.perf_counter()

    content: bytes | None = None
    mime: str | None = None
    extension: str | None = None
    if photo is not None:
        content, mime, extension = validate_upload_or_400(photo)
    logger.info("[Complaint] validation done: %.0fms", (time.perf_counter() - started) * 1000)

    complaint = Complaint(
        student_id=student.id,
        photo_storage_key=None,
        description=description,
        block=normalize_block(block),
        room=room,
        status=ComplaintStatus.SUBMITTED,
    )
    db.add(complaint)
    db.flush()  # generates complaint.id (in this transaction); not yet durable
    _add_history(db, complaint, None, ComplaintStatus.SUBMITTED, student)
    commit_started = time.perf_counter()
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("[DATABASE_ERROR] Could not persist complaint for student %s", student.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the complaint. Please try again shortly.",
        ) from exc
    db.refresh(complaint)
    logger.info(
        "[Complaint] DB insert+commit: %.0fms (complaint %s SUBMITTED, student %s)",
        (time.perf_counter() - commit_started) * 1000,
        complaint.id,
        student.id,
    )

    if content is not None and extension is not None:
        upload_started = time.perf_counter()
        # The photo key write runs in its own post-commit transaction, which
        # the after_begin listener re-stamps with the *student's* RLS context.
        # Students intentionally have no complaints UPDATE policy, so persist
        # this trusted server-side result under the SYSTEM context (same
        # pattern the background AI worker uses), then restore the request
        # context for any follow-up reads in the same request.
        from app.db.database import set_database_security_context  # local import: avoids engine import at module load

        request_context = dict(db.info.get("hosteldesk_security_context") or {})
        set_database_security_context(db, "SYSTEM")
        try:
            complaint.photo_storage_key = get_image_storage().save(
                complaint.id, content, extension
            )
            db.commit()
            db.refresh(complaint)
            logger.info(
                "[Complaint] photo upload: %.0fms",
                (time.perf_counter() - upload_started) * 1000,
            )
        except StorageUnavailableError as exc:
            db.rollback()
            # The complaint itself is already durable; record the failure and
            # keep it recoverable instead of deleting it. Placeholders keep the
            # photograph's history under the SYSTEM context.
            logger.error("Photo storage failed for complaint %s: %s", complaint.id, exc)
            complaint = db.get(Complaint, complaint.id)
            if complaint is not None:
                _add_history(
                    db,
                    complaint,
                    ComplaintStatus.SUBMITTED,
                    ComplaintStatus.SUBMITTED,
                    student,
                    "Photo upload failed - please re-send the photo with the next update.",
                )
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Photo storage is temporarily unavailable. Please try again.",
            ) from exc
        finally:
            db.info["hosteldesk_security_context"] = request_context

    logger.info(
        "[Complaint] response ready: complaint %s in %.2fs (AI runs in background)",
        complaint.id,
        time.perf_counter() - started,
    )
    return complaint, content, mime


def recent_open_complaints(
    db: Session, complaint: Complaint, limit: int = 5
) -> list[dict]:
    """Up to `limit` recent OPEN complaints in the same block (id, room,
    category, first 80 chars) so the model can flag likely duplicates.
    Never includes student identity."""
    stmt = (
        select(Complaint.id, Complaint.room, Complaint.category, Complaint.description)
        .where(
            Complaint.block == complaint.block,
            Complaint.id != complaint.id,
            Complaint.status.in_(
                [ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW]
            ),
        )
        .order_by(Complaint.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": int(row.id),
            "room": row.room,
            "category": row.category.value if row.category else "UNKNOWN",
            "note": (row.description or "")[:80],
        }
        for row in db.execute(stmt).all()
        if row.category is not None  # only classified problems are useful context
    ]


async def process_complaint_ai(complaint_id: int, image: bytes | None, image_mime: str | None) -> None:
    """BACKGROUND task: the one and only Gemini call for a new complaint.

    Runs after the HTTP response using its OWN database session (the request's
    session is closed by then). Guarantees:
      - never deletes a persisted complaint on any AI failure
      - at most one AI analysis per complaint (idempotency guards below)
      - never overwrites a status the warden already moved forward
    """
    from app.db.database import (
        SessionLocal,
        clear_database_security_context,
        set_database_security_context,
    )  # local import: avoids engine import at module load

    db = SessionLocal()
    set_database_security_context(db, "SYSTEM")
    analysis_start = time.perf_counter()
    try:
        complaint = db.get(Complaint, complaint_id)
        if complaint is None:
            logger.error("[AI] Background analysis: complaint %s vanished - aborting.", complaint_id)
            return
        if complaint.status not in (ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW):
            logger.info(
                "[AI] Skipping analysis for complaint %s: status already %s (warden acted first).",
                complaint_id,
                complaint.status.value,
            )
            return
        already_analyzed = db.execute(
            select(AIRecommendation).where(AIRecommendation.complaint_id == complaint_id)
        ).scalar_one_or_none()
        if already_analyzed is not None:
            logger.info("[AI] Skipping analysis for complaint %s: recommendation exists.", complaint_id)
            return

        logger.info("[AI] processing started for complaint %s", complaint_id)
        try:
            await _run_ai_analysis(
                db,
                complaint,
                image,
                image_mime,
                # Guard evaluated AFTER the AI call: the warden may review the
                # complaint while the Gemini request runs.
                status_guard=lambda: db.execute(
                    select(Complaint.status).where(Complaint.id == complaint_id)
                ).scalar_one(),
            )
            db.commit()
            logger.info(
                "[AI] processing finished for complaint %s in %.2fs (recommendation saved, "
                "complaint in WARDEN_REVIEW)",
                complaint_id,
                time.perf_counter() - analysis_start,
            )
        except Exception:  # noqa: BLE001 - AI must never erase a persisted complaint
            db.rollback()
            logger.exception("[AI_ERROR] Background AI failed unexpectedly for complaint %s.", complaint_id)
            complaint = db.get(Complaint, complaint_id)
            if complaint is not None and complaint.status == ComplaintStatus.SUBMITTED:
                _transition(
                    db,
                    complaint,
                    ComplaintStatus.WARDEN_REVIEW,
                    None,
                    "AI analysis crashed - awaiting manual warden review.",
                )
                db.commit()
            logger.info(
                "[AI] complaint %s kept; warden can review it manually.", complaint_id
            )
    finally:
        clear_database_security_context(db)
        db.close()


async def _run_ai_analysis(
    db: Session,
    complaint: Complaint,
    image: bytes | None,
    image_mime: str | None,
    status_guard: Callable[[], ComplaintStatus] | None = None,
) -> None:
    """Call the AI orchestration service once and persist a safe recommendation.

    The AI is only ever called here - exactly once per complaint, from the
    background task scheduled at creation time. Gemini is called with the photo
    bytes + description, and the validated reply is stored as an immutable
    recommendation. ``status_guard`` is evaluated AFTER the AI call returns:
    if it shows the warden already acted during the analysis,
    the recommendation is kept but fields/status are left untouched.
    """
    if image:
        logger.info("AI analysis started for complaint %s (with photo)", complaint.id)
    else:
        logger.info("AI analysis started for complaint %s (text only)", complaint.id)

    recent = recent_open_complaints(db, complaint)
    if recent:
        logger.info(
            "[AI] duplicate-check context for complaint %s: %d recent open complaint(s) in block %s",
            complaint.id,
            len(recent),
            complaint.block,
        )
    result = await ai_service.analyze_complaint(image, image_mime, complaint.description, recent)

    if status_guard is not None:
        fresh_status = status_guard()
        logger.info(
            "Complaint %s: fresh status after AI call is %s.",
            complaint.id,
            fresh_status.value,
        )
    else:
        fresh_status = complaint.status

    # Transitions only make sense for a brand-new, unreviewed complaint.
    allow_transitions = fresh_status is ComplaintStatus.SUBMITTED
    # Fields may be refreshed for SUBMITTED and WARDEN_REVIEW; anything later
    # (ASSIGNED/IN_PROGRESS/COMPLETED) is the warden's decision and stays.
    update_fields = allow_transitions or fresh_status is ComplaintStatus.WARDEN_REVIEW

    if isinstance(result, AIAnalysisResult):
        # Drop a hallucinated duplicate id: it must point at one of the
        # recent open complaints the model was actually shown.
        allowed_duplicate_ids = {item["id"] for item in recent}
        if result.duplicate_of_complaint_id is not None and (
            result.duplicate_of_complaint_id not in allowed_duplicate_ids
        ):
            logger.warning(
                "[AI] dropping hallucinated duplicate_of_complaint_id %s for complaint %s",
                result.duplicate_of_complaint_id,
                complaint.id,
            )
            result.duplicate_of_complaint_id = None

        # Safety escalation: a flagged complaint must never be queued below HIGH.
        if result.safety_flag and result.severity.value != Severity.HIGH.value:
            logger.warning(
                "[AI] safety flag raised severity for complaint %s: %s -> HIGH",
                complaint.id,
                result.severity.value,
            )
            result.severity = Severity.HIGH

        recommendation = AIRecommendation(
            complaint_id=complaint.id,
            category=ComplaintCategory(result.category.value),
            severity=Severity(result.severity.value),
            suggested_worker=WorkerType(result.suggested_worker.value),
            reason=result.reason,
            confidence=result.confidence.value if result.confidence else None,
            safety_flag=result.safety_flag,
            duplicate_of_complaint_id=result.duplicate_of_complaint_id,
            model=result.model,
            raw_response={
                "category": result.category.value,
                "severity": result.severity.value,
                "suggested_worker": result.suggested_worker.value,
            },
        )
        db.add(recommendation)
        db.flush()
        if allow_transitions:
            complaint.category = recommendation.category
            complaint.severity = recommendation.severity
            complaint.ai_suggested_worker = recommendation.suggested_worker
            _transition(db, complaint, ComplaintStatus.AI_ANALYZED, None, "AI analysis")
            _transition(db, complaint, ComplaintStatus.WARDEN_REVIEW, None, "Ready for warden review")
        elif update_fields:
            # Re-analysis while waiting for review: refresh the suggestion
            # fields only - never re-transition the status.
            complaint.category = recommendation.category
            complaint.severity = recommendation.severity
            complaint.ai_suggested_worker = recommendation.suggested_worker
        else:
            # The warden decided while the AI was running: keep only the
            # recommendation, never overwrite the warden's fields/status.
            logger.info(
                "Complaint %s: warden acted during AI analysis - recommendation kept, "
                "fields and status left untouched (%s).",
                complaint.id,
                complaint.status.value,
            )
        logger.info("AI recommendation stored for complaint %s", complaint.id)
        # Repeat-problem insight at submission time: the warden sees the
        # alert immediately, not only after review. Idempotent via
        # evaluate_repeat_problem (one active alert per block+category).
        if update_fields and recommendation.category is not None:
            from app.services import insights_service  # local: avoids import cycle

            db.flush()  # sessions run with autoflush=False: publish fields first
            insights_service.evaluate_repeat_problem(db, complaint)
    else:
        recommendation = AIRecommendation(
            complaint_id=complaint.id,
            raw_response=result.raw_response,
        )
        db.add(recommendation)
        db.flush()
        logger.warning("AI analysis failed for complaint %s: %s", complaint.id, result.raw_response)
        if allow_transitions:
            _transition(
                db,
                complaint,
                ComplaintStatus.WARDEN_REVIEW,
                None,
                "AI unavailable - waiting for manual warden review",
            )


def confirm_resolved(db: Session, user: User, complaint_id: int) -> Complaint:
    """Student confirms the completed fix. History-only: no status change."""
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.student_id != user.id or user.role is not UserRole.STUDENT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found.")
    if complaint.status is not ComplaintStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only completed complaints can be confirmed as resolved.",
        )
    if any(h.note == _CONFIRMED_NOTE for h in (complaint.history or [])):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already confirmed this complaint as resolved."
        )

    def _write() -> None:
        _add_history(
            db, complaint, ComplaintStatus.COMPLETED, ComplaintStatus.COMPLETED, user, _CONFIRMED_NOTE
        )
        db.commit()

    _system_write(db, _write)
    db.refresh(complaint)
    return db.execute(
        select(Complaint).where(Complaint.id == complaint.id).options(selectinload(Complaint.history))
    ).scalar_one()


def reopen_complaint(db: Session, user: User, complaint_id: int, reason: str) -> Complaint:
    """Student reopens a completed complaint; the warden reviews it again."""
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.student_id != user.id or user.role is not UserRole.STUDENT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found.")
    if complaint.status is not ComplaintStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only completed complaints can be reopened.",
        )
    reason = reason.strip()
    if not 5 <= len(reason) <= 300:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Please describe what is still not fixed (5-300 characters).",
        )
    old_status = complaint.status

    def _write() -> None:
        complaint.status = ComplaintStatus.WARDEN_REVIEW
        complaint.completed_at = None
        _add_history(
            db, complaint, old_status, ComplaintStatus.WARDEN_REVIEW, user, f"Reopened by student: {reason}"
        )
        db.commit()

    _system_write(db, _write)
    db.refresh(complaint)
    return db.execute(
        select(Complaint).where(Complaint.id == complaint.id).options(selectinload(Complaint.history))
    ).scalar_one()


def _transition(
    db: Session,
    complaint: Complaint,
    new_status: ComplaintStatus,
    actor: User | None,
    note: str | None,
) -> None:
    old = complaint.status
    complaint.status = new_status
    _add_history(db, complaint, old, new_status, actor, note)


def load_photo_bytes(db: Session, complaint: Complaint) -> tuple[bytes | None, str | None]:
    """Best-effort photo read for re-analysis (None when absent/unavailable)."""
    if not complaint.photo_storage_key:
        return None, None
    from app.utils.storage import EXTENSION_TO_MIME, StorageUnavailableError, get_image_storage

    try:
        storage = get_image_storage()
        content = storage.open_bytes(complaint.photo_storage_key)
    except (FileNotFoundError, StorageUnavailableError, RuntimeError) as exc:
        logger.warning(
            "[AI] re-analysis photo load failed for complaint %s: %s", complaint.id, exc
        )
        return None, None
    suffix = complaint.photo_storage_key.rsplit(".", 1)[-1].lower()
    return content, EXTENSION_TO_MIME.get(suffix)


_REANALYZABLE_status = {ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW}


async def reanalyze_complaint_background(complaint_id: int) -> None:
    """Background re-analysis triggered by the warden.

    Unlike ``process_complaint_ai`` this BYPASSES the recommendation-exists
    guard (a failed first pass stores an error recommendation, and the warden
    re-running the analysis wants a fresh attempt); prior rows are kept as an
    audit trail. Runs on its own session under the SYSTEM context.
    """
    from app.db.database import (
        SessionLocal,
        clear_database_security_context,
        set_database_security_context,
    )

    db = SessionLocal()
    set_database_security_context(db, "SYSTEM")
    try:
        complaint = db.get(Complaint, complaint_id)
        if complaint is None or complaint.status not in _REANALYZABLE_status:
            logger.info(
                "[AI] re-analysis skipped for complaint %s (missing or status moved on).",
                complaint_id,
            )
            return
        image, image_mime = load_photo_bytes(db, complaint)
        await _run_ai_analysis(db, complaint, image, image_mime)
        db.commit()
        logger.info("[AI] re-analysis finished for complaint %s", complaint_id)
    except Exception:  # noqa: BLE001 - never crash the request chain
        db.rollback()
        logger.exception("[AI_ERROR] re-analysis failed unexpectedly for complaint %s.", complaint_id)
    finally:
        clear_database_security_context(db)
        db.close()


def find_stale_submitted_complaints(
    db: Session,
    *,
    max_count: int = 5,
    older_than_seconds: int = 120,
) -> list[Complaint]:
    """SUBMITTED complaints with no recommendation older than the threshold —
    candidates for a bounded background AI sweep."""
    cutoff = utcnow() - timedelta(seconds=older_than_seconds)
    stmt = (
        select(Complaint)
        .where(
            Complaint.status == ComplaintStatus.SUBMITTED,
            Complaint.created_at < cutoff,
            ~Complaint.recommendations.any(),
        )
        .order_by(Complaint.created_at.asc())
        .limit(max_count)
    )
    return list(db.execute(stmt).scalars())


def get_complaint_scoped(db: Session, complaint_id: int, user: User) -> Complaint:
    """Role-based visibility handled server-side."""
    stmt = (
        select(Complaint)
        .where(Complaint.id == complaint_id)
        .options(
            selectinload(Complaint.student),
            selectinload(Complaint.approved_worker).selectinload(Worker.user),
            selectinload(Complaint.history),
            selectinload(Complaint.recommendations),
        )
    )
    complaint = db.execute(stmt).scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found.")

    if user.role == UserRole.STUDENT:
        if complaint.student_id != user.id:
            # Same response as a missing complaint, so other students can't probe.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found.")
        return complaint

    if user.role == UserRole.WARDEN:
        return complaint

    if user.role == UserRole.WORKER:
        worker = db.execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
        if worker is None or complaint.approved_worker_id != worker.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found.")
        if complaint.student is None and complaint.student_id:
            from app.db.database import set_database_security_context
            set_database_security_context(db, "SYSTEM")
            complaint.student = db.get(User, complaint.student_id)
            set_database_security_context(db, "WORKER")
        return complaint

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not supported here.")


def list_complaints(
    db: Session,
    *,
    status_filter: ComplaintStatus | None = None,
    category: ComplaintCategory | None = None,
    severity: Severity | None = None,
    search: str | None = None,
    block: str | None = None,
    needs_review: bool = False,
    sort: str = "newest",
) -> list[Complaint]:
    """Warden-only complaint queue with the students/workers joined in."""
    stmt = (
        select(Complaint)
        .options(
            selectinload(Complaint.student),
            selectinload(Complaint.approved_worker).selectinload(Worker.user),
            selectinload(Complaint.recommendations),
        )
    )
    if status_filter is not None:
        stmt = stmt.where(Complaint.status == status_filter)
    if needs_review:
        stmt = stmt.where(
            Complaint.status.in_(
                [ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW]
            )
        )
    if category is not None:
        stmt = stmt.where(Complaint.category == category)
    if severity is not None:
        stmt = stmt.where(Complaint.severity == severity)
    if block is not None:
        normalized = normalize_block(block)
        if normalized:
            stmt = stmt.where(Complaint.block == normalized)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.join(Complaint.student).where(
            Complaint.description.ilike(term)
            | Complaint.block.ilike(term)
            | Complaint.room.ilike(term)
            | User.name.ilike(term)
        )
    ordering = {
        "newest": Complaint.created_at.desc(),
        "oldest": Complaint.created_at.asc(),
        "updated": Complaint.updated_at.desc(),
        # Pairs with needs_review: "oldest unreviewed first".
        "review": Complaint.created_at.asc(),
    }.get(sort, Complaint.created_at.desc())
    stmt = stmt.order_by(ordering)
    return list(db.execute(stmt).scalars())


def get_worker_for_user(db: Session, user: User) -> Worker:
    worker = db.execute(select(Worker).where(Worker.user_id == user.id)).scalar_one_or_none()
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker profile not found.")
    return worker
