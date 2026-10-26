"""Task endpoints for workers."""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.database import get_db
from app.db.models import User, UserRole
from app.schemas.task import TaskOut, TaskStatusUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])
logger = logging.getLogger(__name__)


@router.get("/my", response_model=list[TaskOut], summary="Tasks assigned to the current worker")
def my_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.WORKER)),
) -> list[TaskOut]:
    return [task_service.as_task_out(task) for task in task_service.list_tasks_for_worker(db, user)]


@router.patch("/{task_id}/status", response_model=TaskOut, summary="Worker updates a task status")
def update_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.WORKER)),
) -> TaskOut:
    task = task_service.update_task_status(db, user, task_id, payload)
    return task_service.as_task_out(task)
