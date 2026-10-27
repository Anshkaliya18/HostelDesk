"""Complaint endpoints (student submit, warden queue, role-scoped detail)."""

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
    Query,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_role
from app.db.database import get_db
from app.db.models import Complaint, ComplaintCategory, ComplaintStatus, Severity, User, UserRole, Worker
from app.schemas.complaint import (
    AIRecommendationOut,
    ComplaintDetailOut,
    ComplaintListItem,
    ReopenRequest,
    ReviewRequest,
    StatusHistoryItem,
    UserBrief,
)
from app.services import complaint_service, task_service
from app.utils.rate_limit import complaint_limiter

router = APIRouter(prefix="/complaints", tags=["Complaints"])
logger = logging.getLogger(__name__)


def _list_item(complaint: Complaint) -> ComplaintListItem:
    student_brief = (
        UserBrief.model_validate(complaint.student)
        if complaint.student
        else UserBrief(id=complaint.student_id, name="Student", role=UserRole.STUDENT)
    )
    recommendation = complaint.recommendations[-1] if complaint.recommendations else None
    return ComplaintListItem(
        id=complaint.id,
        student=student_brief,
        block=complaint.block,
        room=complaint.room,
        description=complaint.description,
        category=complaint.category,
        severity=complaint.severity,
        ai_suggested_worker=complaint.ai_suggested_worker,
        approved_worker=(
            {
                "id": complaint.approved_worker.id,
                "worker_type": complaint.approved_worker.worker_type,
                "name": complaint.approved_worker.user.name,
            }
            if complaint.approved_worker and complaint.approved_worker.user
            else None
        ),
        status=complaint.status,
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
        completed_at=complaint.completed_at,
        ai_confidence=recommendation.confidence if recommendation else None,
        ai_safety_flag=(
            bool(recommendation.safety_flag)
            if recommendation is not None and recommendation.safety_flag is not None
            else None
        ),
    )


def _detail(complaint: Complaint) -> ComplaintDetailOut:
    base = _list_item(complaint)
    recommendation = complaint.recommendations[-1] if complaint.recommendations else None
    return ComplaintDetailOut(
        **base.model_dump(),
        photo_available=bool(complaint.photo_storage_key),
        warden_note=complaint.warden_note,
        worker_note=complaint.worker_note,
        history=[StatusHistoryItem.model_validate(h) for h in (complaint.history or [])],
        ai_recommendation=AIRecommendationOut.model_validate(recommendation) if recommendation else None,
    )


def _enforce_complaint_rate_limits(student_id: int) -> None:
    """5 complaints per 10 minutes and 20 per day per student (sliding window)."""
    if not complaint_limiter.check(
        f"complaint-10min:{student_id}",
        settings.complaint_rate_limit_10min,
        10 * 60,
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You have sent several reports in a short time. Please wait a few "
            "minutes before reporting again.",
        )
    if not complaint_limiter.check(
        f"complaint-day:{student_id}",
        settings.complaint_rate_limit_daily,
        24 * 60 * 60,
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Daily reporting limit reached. Please wait until tomorrow or "
            "contact the warden directly for urgent issues.",
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ComplaintDetailOut,
    summary="Student submits a complaint (photo optional)",
)
def submit_complaint(
    description: Annotated[str, Form(min_length=10, max_length=1000)],
    block: Annotated[str, Form(min_length=1, max_length=40)],
    room: Annotated[str, Form(min_length=1, max_length=60)],
    photo: Annotated[UploadFile | None, File()] = None,
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    student: User = Depends(require_role(UserRole.STUDENT)),
    db: Session = Depends(get_db),
) -> ComplaintDetailOut:
    """FAST RESPONSE: persist the complaint, then return without waiting for AI.

    BackgroundTasks schedules the one-and-only AI analysis after the response;
    it runs with its own DB session and can never erase the persisted row.
    """
    _enforce_complaint_rate_limits(student.id)
    complaint, image, image_mime = complaint_service.create_complaint(
        db, student, description.strip(), block.strip(), room.strip(), photo
    )
    background_tasks.add_task(
        complaint_service.process_complaint_ai, complaint.id, image, image_mime
    )
    loaded = db.get(Complaint, complaint.id)
    return _detail(loaded)


@router.get("", response_model=list[ComplaintListItem], summary="Warden complaint queue")
def warden_queue(
    status_filter: ComplaintStatus | None = Query(default=None, alias="status"),
    category: ComplaintCategory | None = None,
    severity: Severity | None = None,
    search: str | None = Query(default=None, max_length=120),
    block: str | None = Query(default=None, max_length=40),
    needs_review: bool = Query(default=False),
    sort: str = Query(default="newest", pattern="^(newest|oldest|updated|review)$"),
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> list[ComplaintListItem]:
    logger.info("Warden %s requested complaint queue", warden.id)
    return [_list_item(c) for c in complaint_service.list_complaints(
        db,
        status_filter=status_filter,
        category=category,
        severity=severity,
        search=search,
        block=block,
        needs_review=needs_review,
        sort=sort,
    )]


@router.get("/mine", response_model=list[ComplaintListItem], summary="Complaints submitted by the signed-in Student")
def my_complaints(db: Session = Depends(get_db),
                  student: User = Depends(require_role(UserRole.STUDENT))) -> list[ComplaintListItem]:
    rows = db.execute(
        select(Complaint).where(Complaint.student_id == student.id)
        .options(
            selectinload(Complaint.student),
            selectinload(Complaint.approved_worker).selectinload(Worker.user),
        )
        .order_by(Complaint.created_at.desc())
    ).scalars().all()
    return [_list_item(c) for c in rows]


@router.get("/{complaint_id}", response_model=ComplaintDetailOut, summary="Complaint detail (role-scoped)")
def complaint_detail(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ComplaintDetailOut:
    complaint = complaint_service.get_complaint_scoped(db, complaint_id, user)
    return _detail(complaint)


@router.post(
    "/{complaint_id}/confirm",
    response_model=ComplaintDetailOut,
    summary="Student confirms a completed complaint as resolved",
)
def confirm_resolved(
    complaint_id: int,
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
) -> ComplaintDetailOut:
    """History-only confirmation (status stays COMPLETED); the student owns this."""
    complaint = complaint_service.confirm_resolved(db, student, complaint_id)
    return _detail(complaint)


@router.post(
    "/{complaint_id}/reopen",
    response_model=ComplaintDetailOut,
    summary="Student reopens a completed complaint with a reason",
)
def reopen_complaint(
    complaint_id: int,
    payload: ReopenRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
) -> ComplaintDetailOut:
    """Moves the complaint back to WARDEN_REVIEW so the warden can decide again."""
    complaint = complaint_service.reopen_complaint(db, student, complaint_id, payload.reason)
    return _detail(complaint)


@router.post(
    "/{complaint_id}/reanalyze",
    response_model=ComplaintDetailOut,
    summary="Warden re-runs the AI analysis (warden only)",
)
async def reanalyze_complaint(
    complaint_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> ComplaintDetailOut:
    """Re-analyze a complaint that has no (usable) recommendation yet.

    The gemini call runs in the background so the response stays fast; the
    prior recommendation rows are preserved as an audit trail.
    """
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found.")
    if complaint.status not in complaint_service._REANALYZABLE_status:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Complaint is in '{complaint.status.value}' and cannot be re-analyzed.",
        )
    image, image_mime = complaint_service.load_photo_bytes(db, complaint)
    background_tasks.add_task(
        complaint_service.reanalyze_complaint_background, complaint_id
    )
    logger.info("Warden %s scheduled AI re-analysis for complaint %s", warden.id, complaint_id)
    return _detail(complaint)


@router.patch(
    "/{complaint_id}/review",
    response_model=ComplaintDetailOut,
    summary="Warden reviews a complaint and assigns a worker",
)
def review_complaint(
    complaint_id: int,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> ComplaintDetailOut:
    """The warden accepts or edits the AI suggestion and picks the final worker."""
    logger.info("Warden review requested for complaint %s", complaint_id)
    task = task_service.review_complaint(db, warden, complaint_id, payload)
    logger.info("Task %s created from warden review", task.id)
    complaint = db.get(Complaint, complaint_id)
    return _detail(complaint)


@router.get("/{complaint_id}/photo", summary="Fetch the private complaint photo (bytes)")
def complaint_photo(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Streams the stored photo back to the frontend; never exposes storage keys."""
    from app.utils.storage import EXTENSION_TO_MIME, get_image_storage

    complaint = complaint_service.get_complaint_scoped(db, complaint_id, user)
    if not complaint.photo_storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint has no photo.")
    storage = get_image_storage()
    try:
        content = storage.open_bytes(complaint.photo_storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo file is missing.") from exc
    suffix = complaint.photo_storage_key.rsplit(".", 1)[-1].lower()
    return Response(
        content=content,
        media_type=EXTENSION_TO_MIME.get(suffix, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="complaint-{complaint_id}.{suffix}"',
            "Cache-Control": "private, max-age=0, no-store",
        },
    )


@router.get(
    "/{complaint_id}/photo/url",
    summary="Temporary signed URL for the private photo (Supabase Storage)",
)
def complaint_photo_signed_url(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Returns a short-lived signed URL instead of the raw bucket object."""
    from app.core.config import settings
    from app.utils.storage import get_image_storage

    complaint = complaint_service.get_complaint_scoped(db, complaint_id, user)
    if not complaint.photo_storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint has no photo.")
    storage = get_image_storage()
    if not storage.supports_signed_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signed URLs are only available when Supabase Storage is configured.",
        )
    expires_in = settings.signed_url_expiry_seconds
    return {
        "url": storage.create_signed_url(complaint.photo_storage_key, expires_in),
        "expires_in": expires_in,
    }
