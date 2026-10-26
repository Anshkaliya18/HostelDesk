"""SQLAlchemy 2.x models for HostelDesk."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---- Enums -----------------------------------------------------------------


class UserRole(str, enum.Enum):
    STUDENT = "STUDENT"
    WARDEN = "WARDEN"
    WORKER = "WORKER"


class WorkerType(str, enum.Enum):
    ELECTRICIAN = "ELECTRICIAN"
    PLUMBER = "PLUMBER"
    CLEANER = "CLEANER"
    CARPENTER = "CARPENTER"


class ComplaintCategory(str, enum.Enum):
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    CLEANING = "CLEANING"
    FURNITURE = "FURNITURE"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ComplaintStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    AI_ANALYZED = "AI_ANALYZED"
    WARDEN_REVIEW = "WARDEN_REVIEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class TaskStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class AlertType(str, enum.Enum):
    REPEAT_PROBLEM = "REPEAT_PROBLEM"


# ---- Tables ----------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    block: Mapped[str | None] = mapped_column(String(40), nullable=True)
    room: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    worker_type: Mapped[WorkerType] = mapped_column(Enum(WorkerType), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship("User")


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    photo_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    block: Mapped[str] = mapped_column(String(40), nullable=False)
    room: Mapped[str] = mapped_column(String(60), nullable=False)
    category: Mapped[ComplaintCategory | None] = mapped_column(Enum(ComplaintCategory), nullable=True)
    severity: Mapped[Severity | None] = mapped_column(Enum(Severity), nullable=True)
    ai_suggested_worker: Mapped[WorkerType | None] = mapped_column(
        Enum(WorkerType), nullable=True
    )
    approved_worker_id: Mapped[int | None] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ComplaintStatus] = mapped_column(
        Enum(ComplaintStatus), default=ComplaintStatus.SUBMITTED, nullable=False, index=True
    )
    warden_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    student: Mapped[User] = relationship("User", foreign_keys=[student_id])
    approved_worker: Mapped[Worker | None] = relationship("Worker", foreign_keys=[approved_worker_id])
    recommendations: Mapped[list["AIRecommendation"]] = relationship(
        "AIRecommendation", back_populates="complaint", order_by="AIRecommendation.id"
    )
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="complaint")
    history: Mapped[list["StatusHistory"]] = relationship(
        "StatusHistory", back_populates="complaint", order_by="StatusHistory.id"
    )


Index("ix_complaints_block_category_created", Complaint.block, Complaint.category, Complaint.created_at)


class AIRecommendation(Base):
    """Preserves every AI analysis. The warden's decision is stored on the
    complaint itself - never written into this table."""

    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[ComplaintCategory | None] = mapped_column(Enum(ComplaintCategory), nullable=True)
    severity: Mapped[Severity | None] = mapped_column(Enum(Severity), nullable=True)
    suggested_worker: Mapped[WorkerType | None] = mapped_column(Enum(WorkerType), nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    complaint: Mapped[Complaint] = relationship("Complaint", back_populates="recommendations")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("workers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.ASSIGNED, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    complaint: Mapped[Complaint] = relationship("Complaint", back_populates="tasks")
    worker: Mapped[Worker] = relationship("Worker")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_status: Mapped[ComplaintStatus | None] = mapped_column(Enum(ComplaintStatus), nullable=True)
    new_status: Mapped[ComplaintStatus] = mapped_column(Enum(ComplaintStatus), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    complaint: Mapped[Complaint] = relationship("Complaint", back_populates="history")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), nullable=False)
    block: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    category: Mapped[ComplaintCategory] = mapped_column(Enum(ComplaintCategory), nullable=False)
    complaint_count: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
