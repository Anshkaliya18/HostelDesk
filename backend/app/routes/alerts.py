"""Alert endpoints (warden-only repeat-problem alerts)."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.database import get_db
from app.db.models import Alert, ComplaintCategory, User, UserRole
from app.services import insights_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])


class AlertOut(BaseModel):
    id: int
    alert_type: str
    block: str
    category: ComplaintCategory
    complaint_count: int
    message: str
    created_at: object
    resolved_at: object

    model_config = ConfigDict(from_attributes=True)


def _alert_out(alert: Alert) -> AlertOut:
    return AlertOut.model_construct(
        id=alert.id,
        alert_type=alert.alert_type.value,
        block=alert.block,
        category=alert.category,
        complaint_count=alert.complaint_count,
        message=alert.message,
        created_at=alert.created_at.isoformat(),
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
    )


@router.get("", response_model=list[AlertOut], summary="Repeat-problem alerts")
def list_alerts(
    alert_status: str = Query(
        default="active",
        alias="status",
        pattern="^(active|resolved|all)$",
        description="Lifecycle filter: active (default), resolved, or all.",
    ),
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> list[AlertOut]:
    alerts = insights_service.list_alerts(db, alert_status)
    return [_alert_out(alert) for alert in alerts]


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertOut,
    summary="Mark a repeat-problem alert resolved (warden-only)",
)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> AlertOut:
    """Explicit warden action; the resolution timestamp is set server-side."""
    alert = insights_service.resolve_alert(db, alert_id)
    return _alert_out(alert)
