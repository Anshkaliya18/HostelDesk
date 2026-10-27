"""Pydantic schemas for complaint endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    ComplaintCategory,
    ComplaintStatus,
    Severity,
    UserRole,
    WorkerType,
)


class UserBrief(BaseModel):
    id: int
    name: str
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class WorkerBrief(BaseModel):
    id: int
    worker_type: WorkerType
    name: str


class AIRecommendationOut(BaseModel):
    id: int
    category: ComplaintCategory | None
    severity: Severity | None
    suggested_worker: WorkerType | None
    reason: str | None = None
    confidence: str | None = None
    safety_flag: bool | None = None
    duplicate_of_complaint_id: int | None = None
    model: str | None = None
    raw_response: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StatusHistoryItem(BaseModel):
    old_status: ComplaintStatus | None
    new_status: ComplaintStatus
    changed_by: int | None
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewRequest(BaseModel):
    category: ComplaintCategory
    severity: Severity
    worker_id: int
    warden_note: str | None = None


class ReopenRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class ComplaintListItem(BaseModel):
    id: int
    student: UserBrief
    block: str
    room: str
    description: str
    category: ComplaintCategory | None
    severity: Severity | None
    ai_suggested_worker: WorkerType | None
    approved_worker: WorkerBrief | None
    status: ComplaintStatus
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None
    # Latest AI recommendation summary for the warden queue (optional so old
    # rows and student endpoints without a recommendation still serialize).
    ai_confidence: str | None = None
    ai_safety_flag: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class ComplaintDetailOut(ComplaintListItem):
    photo_available: bool
    warden_note: str | None
    worker_note: str | None
    history: list[StatusHistoryItem] = []
    ai_recommendation: AIRecommendationOut | None = None
