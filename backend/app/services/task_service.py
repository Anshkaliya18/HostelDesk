"""Task service: the warden's review gate and worker task lifecycle."""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Complaint,
    ComplaintStatus,
    StatusHistory,
    Task,
    TaskStatus,
    User,
    Worker,
)
from app.schemas.complaint import ReviewRequest
from app.schemas.task import TaskStatusUpdate

logger = logging.getLogger(__name__)

_REVIEWABLE_STATUSES = {ComplaintStatus.SUBMITTED, ComplaintStatus.WARDEN_REVIEW, ComplaintStatus.AI_ANALYZED}

# Allowed task transitions (worker controlled)
_ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.ASSIGNED: {TaskStatus.IN_PROGRESS},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED},
    TaskStatus.COMPLETED: set(),
}


def review_complaint(
    db: Session,
    warden: User,
    complaint_id: int,
    payload: ReviewRequest,
) -> Task:
    """Warden decision gate: set final category/severity/worker, create the task.

    The original AI recommendation row is never modified.
    """
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found.")
    if complaint.status not in _REVIEWABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Complaint is already in '{complaint.status.value}' and cannot be reviewed again.",
        )

    worker = db.get(Worker, payload.worker_id)
    if worker is None or not worker.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Selected worker is not available.")

    task = Task(complaint_id=complaint.id, worker_id=worker.id, status=TaskStatus.ASSIGNED)
    db.add(task)

    complaint.category = payload.category
    complaint.severity = payload.severity
    complaint.approved_worker_id = worker.id
    complaint.warden_note = payload.warden_note

    old_status = complaint.status
    complaint.status = ComplaintStatus.ASSIGNED
    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=old_status,
            new_status=ComplaintStatus.ASSIGNED,
            changed_by=warden.id,
            note=payload.warden_note,
        )
    )
    db.flush()

    logger.info(
        "Warden %s reviewed complaint %s: worker=%s category=%s severity=%s",
        warden.id,
        complaint.id,
        worker.id,
        payload.category.value,
        payload.severity.value,
    )

    from app.services import insights_service

    insights_service.evaluate_repeat_problem(db, complaint)
    db.commit()
    db.refresh(task)
    return task


def get_task_for_worker(db: Session, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")
    task = db.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.complaint))
    ).scalar_one()
    worker = complaint_worker(db, user)
    if task.worker_id != worker.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")
    return task


def complaint_worker(db: Session, user: User) -> Worker:
    worker = db.execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    if worker is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker profile not found.")
    return worker


def list_tasks_for_worker(db: Session, user: User) -> list[Task]:
    worker = complaint_worker(db, user)
    stmt = (
        select(Task)
        .where(Task.worker_id == worker.id)
        .options(
            selectinload(Task.complaint).selectinload(Complaint.approved_worker),
            selectinload(Task.complaint).selectinload(Complaint.history),
            selectinload(Task.complaint).selectinload(Complaint.recommendations),
        )
        .order_by(Task.assigned_at.desc())
    )
    return list(db.execute(stmt).scalars())


def update_task_status(
    db: Session,
    user: User,
    task_id: int,
    payload: TaskStatusUpdate,
) -> Task:
    task_stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.complaint), selectinload(Task.worker).selectinload(Worker.user))
    )
    task = db.execute(task_stmt).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")

    worker = complaint_worker(db, user)
    if task.worker_id != worker.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")

    complaint = task.complaint
    allowed = _ALLOWED_TASK_TRANSITIONS.get(task.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot move task from '{task.status.value}' to '{payload.status.value}'.",
        )

    now = datetime.now(timezone.utc)
    old_complaint_status = complaint.status
    if payload.status is TaskStatus.IN_PROGRESS:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now
        complaint.status = ComplaintStatus.IN_PROGRESS
    else:  # COMPLETED
        task.status = TaskStatus.COMPLETED
        task.completed_at = now
        complaint.status = ComplaintStatus.COMPLETED
        complaint.completed_at = now
        if payload.note:
            task.note = payload.note
            complaint.worker_note = payload.note

    task.note = task.note or payload.note
    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=old_complaint_status,
            new_status=complaint.status,
            changed_by=user.id,
            note=payload.note,
        )
    )
    db.commit()
    db.refresh(task)
    logger.info("Task %s moved to %s by worker %s", task.id, task.status.value, user.id)
    return task


def as_task_out(task: Task):
    """Build TaskOut (category/severity conveniences come from the complaint)."""
    from app.schemas.task import TaskOut

    return TaskOut(
        id=task.id,
        complaint_id=task.complaint_id,
        category=task.complaint.category,
        description=task.complaint.description,
        block=task.complaint.block,
        room=task.complaint.room,
        severity=task.complaint.severity,
        status=task.status,
        note=task.note,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def worker_worker_type() -> str:
    """Legacy helper kept for convenience."""
    return "ELECTRICIAN"

