"""Warden dashboard, worker directory, and operational reports."""

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_role
from app.db.database import get_db
from app.db.models import AIRecommendation, Complaint, ComplaintStatus, Task, TaskStatus, User, UserRole, Worker
from app.services import complaint_service, insights_service
from app.routes.complaints import _list_item

router = APIRouter(prefix="/warden", tags=["Warden"])


class WorkerOut(BaseModel):
    id: int
    name: str
    worker_type: str
    is_active: bool
    active_tasks: int


@router.get("/dashboard", summary="Warden dashboard metrics and recent complaints")
def dashboard(db: Session = Depends(get_db), _warden: User = Depends(require_role(UserRole.WARDEN))):
    complaints = complaint_service.list_complaints(db)
    tasks = list(db.execute(select(Task)).scalars())
    active_tasks = [t for t in tasks if t.status != TaskStatus.COMPLETED]
    workers = db.execute(select(Worker).options(selectinload(Worker.user))).scalars().all()
    return {
        "total": len(complaints),
        "pending": sum(c.status in (ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW) for c in complaints),
        "in_progress": sum(c.status in (ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS) for c in complaints),
        "resolved": sum(c.status == ComplaintStatus.COMPLETED for c in complaints),
        "high_priority": sum(c.severity is not None and c.severity.value == "HIGH" and c.status != ComplaintStatus.COMPLETED for c in complaints),
        "awaiting_assignment": sum(c.status in (ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW) for c in complaints),
        "recent": [_list_item(c).model_dump(mode="json") for c in complaints[:6]],
        "workers": [
            {"id": w.id, "name": w.user.name, "worker_type": w.worker_type.value,
             "is_active": w.is_active,
             "active_tasks": sum(t.worker_id == w.id for t in active_tasks)}
            for w in workers
        ],
    }


@router.get("/workers", response_model=list[WorkerOut], summary="List workers and current workload")
def workers_list(db: Session = Depends(get_db), _warden: User = Depends(require_role(UserRole.WARDEN))):
    workers = db.execute(select(Worker).options(selectinload(Worker.user))).scalars().all()
    tasks = db.execute(select(Task).where(Task.status != TaskStatus.COMPLETED)).scalars().all()
    return [WorkerOut(id=w.id, name=w.user.name, worker_type=w.worker_type.value,
                      is_active=w.is_active, active_tasks=sum(t.worker_id == w.id for t in tasks))
            for w in workers]


@router.post("/ai-sweep", summary="Background sweep of stale unanalyzed complaints (warden only)")
def ai_sweep(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _warden: User = Depends(require_role(UserRole.WARDEN)),
) -> dict:
    """Bounded self-healing sweep: pick up to 5 SUBMITTED complaints that are
    older than 2 minutes and have no recommendation, and schedule their AI
    analysis in the background (covers a failed/cold AI pipeline)."""
    stale = complaint_service.find_stale_submitted_complaints(db)
    for complaint in stale:
        background_tasks.add_task(complaint_service.process_complaint_ai, complaint.id, None, None)
    return {"scheduled": [complaint.id for complaint in stale]}


@router.get("/reports", summary="Warden operational report")
def reports(db: Session = Depends(get_db), _warden: User = Depends(require_role(UserRole.WARDEN))):
    complaints = list(db.execute(select(Complaint)).scalars())
    # AI_ANALYZED is a transient status (the background worker moves
    # complaints to WARDEN_REVIEW seconds after submission), so it is never
    # observable in a report. The meaningful number is how many complaints
    # actually carry an AI recommendation.
    ai_analyzed = len(
        set(
            db.execute(select(AIRecommendation.complaint_id)).scalars().all()
        )
    )
    return {
        "digest": insights_service.build_daily_digest(db),
        "ai_analyzed": ai_analyzed,
        "by_status": {s.value: sum(c.status == s for c in complaints) for s in ComplaintStatus},
        "by_category": {
            category: sum(c.category is not None and c.category.value == category for c in complaints)
            for category in ("ELECTRICAL", "PLUMBING", "CLEANING", "FURNITURE")
        },
    }
