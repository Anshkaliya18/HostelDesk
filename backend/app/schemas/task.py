"""Pydantic schemas for task endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import ComplaintCategory, Severity, TaskStatus, WorkerType


class TaskOut(BaseModel):
    id: int
    complaint_id: int
    category: ComplaintCategory | None
    description: str
    block: str
    room: str
    severity: Severity | None
    status: TaskStatus
    note: str | None
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    note: str | None = None


class TaskWorkerInfo(BaseModel):
    id: int
    worker_type: WorkerType
    name: str
