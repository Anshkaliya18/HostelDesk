"""Alert endpoints (warden-only repeat-problem alerts)."""

from fastapi import APIRouter, Depends
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


@router.get("", response_model=list[AlertOut], summary="Active repeat-problem alerts")
def active_alerts(
    db: Session = Depends(get_db),
    warden: User = Depends(require_role(UserRole.WARDEN)),
) -> list[AlertOut]:
    alerts = insights_service.list_active_alerts(db)
    result: list[AlertOut] = []
    for alert in alerts:
        result.append(
            AlertOut.model_construct(
                id=alert.id,
                alert_type=alert.alert_type.value,
                block=alert.block,
                category=alert.category,
                complaint_count=alert.complaint_count,
                message=alert.message,
                created_at=alert.created_at.isoformat(),
                resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
            )
        )
    return result
