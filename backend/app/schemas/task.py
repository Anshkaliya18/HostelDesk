"""Pydantic schemas for task endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

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

    @model_validator(mode="after")
    def require_note_on_completion(self) -> "TaskStatusUpdate":
        """The completion note is the worker's record of what was done."""
        if self.status is TaskStatus.COMPLETED:
            note = (self.note or "").strip()
            if len(note) < 5:
                raise ValueError(
                    "A completion note of at least 5 characters is required when marking a task completed."
                )
        return self


class TaskWorkerInfo(BaseModel):
    id: int
    worker_type: WorkerType
    name: str
