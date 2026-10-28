"""Insights / rules service: deterministic repeat-problem alerts + daily digest.

No AI here. Everything is plain database rules so the warden digest never
depends on Gemini.
"""

import logging
from datetime import date, timedelta, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Alert,
    AlertType,
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    Task,
    TaskStatus,
)
from app.utils.normalize import normalize_block

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware ones. Normalize."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def evaluate_repeat_problem(db: Session, complaint: Complaint) -> Alert | None:
    """Rule: 3+ complaints for the same (block, category) inside the window
    create (or refresh) one REPEAT_PROBLEM alert."""
    if complaint.category is None:
        return None

    block = normalize_block(complaint.block) or complaint.block
    window_start = _utcnow() - timedelta(days=settings.repeat_problem_window_days)
    count_stmt = select(func.count()).select_from(Complaint).where(
        Complaint.block == block,
        Complaint.category == complaint.category,
        Complaint.created_at >= window_start,
    )
    complaint_count = int(db.execute(count_stmt).scalar_one())

    existing = db.execute(
        select(Alert).where(
            Alert.block == block,
            Alert.category == complaint.category,
            Alert.resolved_at.is_(None),
        )
    ).scalar_one_or_none()

    if complaint_count < settings.repeat_problem_threshold:
        return existing

    window_days = settings.repeat_problem_window_days
    if existing is None:
        alert = Alert(
            alert_type=AlertType.REPEAT_PROBLEM,
            block=block,
            category=complaint.category,
            complaint_count=complaint_count,
            message=(
                f"{complaint.category.value} issues repeat in {block} Block: "
                f"{complaint_count} complaints in the last {window_days} days."
            ),
        )
        db.add(alert)
        db.flush()
        logger.info(
            "Repeat-problem alert generated for %s / %s (count=%d)",
            block,
            complaint.category.value,
            complaint_count,
        )
        return alert

    existing.complaint_count = complaint_count
    existing.message = (
        f"{complaint.category.value} issues repeat in {existing.block} Block: "
        f"{complaint_count} complaints in the last {window_days} days."
    )
    db.flush()
    return existing


# ---- Optional AI polish of the digest summary -------------------------------

_DIGEST_CACHE: dict[str, tuple[float, str]] = {}
_DIGEST_CACHE_TTL_SECONDS = 15 * 60
_DIGEST_TIMEOUT_SECONDS = 8

_DIGEST_PROMPT = """You are the warden's assistant for a hostel maintenance desk.
Write a short, clear daily briefing using ONLY the JSON counters below.
Return exactly three plain-text lines with these labels:
Activity: new reports and completed today.
Queue: open complaints, delayed reviews, and overdue tasks.
Patterns: active repeat alerts and the leading hotspot, if one exists.
Use the exact numbers provided. Keep the full response under 55 words. No names,
recommendations, invented causes, markdown, greeting, or extra sentences.
Tone: calm, factual, direct.

Counters: {payload}

Reply with ONLY the digest sentences."""


async def ai_polish_digest(digest: dict) -> str | None:
    """One Gemini text call to reword the rules-based digest.

    Never sends student identities or photos - only counters. Cached for 15
    minutes; silently returns None (keep the rules summary) on any problem.
    """
    import json as _json
    import time as _time

    import httpx

    from app.services.ai_service import GEMINI_API_BASE_URL, _uses_thinking

    if not settings.digest_ai_polish or not settings.gemini_api_key:
        return None

    payload = _json.dumps(
        {
            "date": digest.get("date"),
            "new_reports": digest.get("submitted_today"),
            "open": digest.get("open_complaints"),
            "overdue": digest.get("overdue_complaints"),
            "completed_today": digest.get("completed_complaints"),
            "recurring_issues": digest.get("recurring_issues"),
            "stale_review": digest.get("stale_review"),
            "categories": digest.get("category_counts"),
            "hotspots": digest.get("hotspots"),
            "oldest_open": digest.get("oldest_open"),
        },
        sort_keys=True,
    )
    cached = _DIGEST_CACHE.get(payload)
    now = _time.monotonic()
    if cached and now - cached[0] < _DIGEST_CACHE_TTL_SECONDS:
        return cached[1]

    model = settings.gemini_model
    generation_config: dict = {
        "temperature": 0,
        "maxOutputTokens": settings.gemini_max_output_tokens,
    }
    if _uses_thinking(model):
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GEMINI_API_BASE_URL}/models/{model}:generateContent",
                json={
                    "contents": [
                        {"role": "user", "parts": [{"text": _DIGEST_PROMPT.format(payload=payload)}]}
                    ],
                    "generationConfig": generation_config,
                },
                headers={"x-goog-api-key": settings.gemini_api_key},
                timeout=_DIGEST_TIMEOUT_SECONDS,
            )
        if response.status_code >= 400:
            logger.warning("[Digest] AI polish skipped: HTTP %s", response.status_code)
            return None
        candidate = (response.json().get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        if not text or len(text) > 1200:
            return None
        _DIGEST_CACHE[payload] = (now, text)
        return text
    except Exception as exc:  # noqa: BLE001 - digest must never depend on AI
        logger.warning("[Digest] AI polish skipped: %s", exc)
        return None


def list_active_alerts(db: Session) -> list[Alert]:
    stmt = (
        select(Alert)
        .where(Alert.resolved_at.is_(None))
        .order_by(Alert.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def list_alerts(db: Session, alert_status: str = "active") -> list[Alert]:
    """Repeat-problem alerts filtered by lifecycle state.

    alert_status: "active" (default, unresolved), "resolved", or "all".
    """
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if alert_status == "active":
        stmt = stmt.where(Alert.resolved_at.is_(None))
    elif alert_status == "resolved":
        stmt = stmt.where(Alert.resolved_at.is_not(None))
    return list(db.execute(stmt).scalars())


def resolve_alert(db: Session, alert_id: int) -> Alert:
    """Warden explicitly marks a repeat-problem alert as resolved.

    The timestamp is set server-side and never accepted from the client.
    Resolution is never implicit: opening or reviewing a complaint does not
    resolve anything. Because active-alert lookups ignore resolved rows, a
    genuine recurrence detected after resolution creates a fresh alert
    instead of being silently folded into the resolved one.
    """
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )
    if alert.resolved_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert is already resolved.",
        )
    alert.resolved_at = _utcnow()
    db.commit()
    logger.info("Repeat-problem alert %s marked resolved", alert_id)
    return alert


def _is_overdue(task: Task) -> bool:
    if task.status not in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
        return False
    threshold_hours = _overdue_hours_for(task.complaint.severity if task.complaint else None)
    threshold = _utcnow() - timedelta(hours=threshold_hours)
    reference = task.started_at or task.assigned_at
    if reference is None:
        return False
    return _as_utc(reference) < threshold


def _overdue_hours_for(severity) -> int:
    """Severity-based SLA; falls back to the legacy single setting."""
    if severity is not None:
        value = getattr(severity, "value", severity)
        mapped = {
            "HIGH": settings.task_overdue_hours_high,
            "MEDIUM": settings.task_overdue_hours_medium,
            "LOW": settings.task_overdue_hours_low,
        }.get(value)
        if mapped is not None:
            return mapped
    return settings.task_overdue_hours


def _rules_summary(
    *,
    open_count: int,
    overdue_count: int,
    submitted_today: int,
    completed_today: int,
    hotspots: list[dict],
    oldest_open: dict | None,
    stale_review_count: int,
    recurring_count: int,
) -> tuple[str, list[str]]:
    """Deterministic three-line digest plus short highlight bullets."""
    activity = f"Activity: {submitted_today} new reports; {completed_today} completed today."
    queue = (
        f"Queue: {open_count} open; {stale_review_count} delayed reviews; "
        f"{overdue_count} overdue tasks."
    )
    if hotspots:
        top = hotspots[0]
        pattern = (
            f"Patterns: {recurring_count} active repeat alerts; busiest is {top['block']} Block, "
            f"{top['category'].replace('_', ' ').title()} ({top['count']} reports in 30 days)."
        )
    else:
        pattern = f"Patterns: {recurring_count} active repeat alerts; no 30-day hotspot detected."
    summary = "\n".join((activity, queue, pattern))

    highlights: list[str] = []
    for spot in hotspots:
        highlights.append(
            f"{spot['count']} {spot['category'].replace('_', ' ').title()} reports in {spot['block']} Block (30 days)"
        )
    if oldest_open is not None and oldest_open["age_hours"] >= 24:
        highlights.append(
            f"Complaint #{oldest_open['id']} ({oldest_open['block']}/{oldest_open['room']}) open for "
            f"{oldest_open['age_hours']:.0f} hours"
        )
    if overdue_count:
        highlights.append(f"{overdue_count} task(s) overdue against the SLA")
    if completed_today:
        highlights.append(f"{completed_today} resolved today")
    return summary, highlights


def build_daily_digest(db: Session, day: date | None = None) -> dict:
    """Deterministic daily summary for the warden. Plain DB rules only."""
    if day is None:
        day = _utcnow().date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    complaints = db.execute(select(Complaint)).scalars().all()

    open_complaints = [c for c in complaints if c.status != ComplaintStatus.COMPLETED]

    overdue_complaints = []
    for complaint in complaints:
        for task in complaint.tasks if complaint.tasks else []:
            if _is_overdue(task):
                overdue_complaints.append(complaint)
                break

    completed_today = [
        c
        for c in complaints
        if c.completed_at is not None and day_start <= _as_utc(c.completed_at) < day_end
    ]
    created_today = [c for c in complaints if day_start <= _as_utc(c.created_at) < day_end]

    category_counts = {category.value: 0 for category in ComplaintCategory}
    for complaint in created_today:
        if complaint.category is not None:
            category_counts[complaint.category.value] += 1

    recurring = list_active_alerts(db)

    # Hotspots: top block+category by complaint count over the last 30 days.
    hotspot_start = _utcnow() - timedelta(days=30)
    hotspots: list[dict] = []
    for complaint in complaints:
        if complaint.category is None or _as_utc(complaint.created_at) < hotspot_start:
            continue
        hotspots.append({"block": complaint.block, "category": complaint.category.value})
    hotspot_counts: dict[tuple[str, str], int] = {}
    for spot in hotspots:
        key = (spot["block"], spot["category"])
        hotspot_counts[key] = hotspot_counts.get(key, 0) + 1
    top_hotspots = [
        {"block": block, "category": category, "count": count}
        for (block, category), count in sorted(
            hotspot_counts.items(), key=lambda item: item[1], reverse=True
        )[:3]
    ]

    oldest_open = None
    if open_complaints:
        oldest = min(open_complaints, key=lambda c: _as_utc(c.created_at))
        oldest_open = {
            "id": oldest.id,
            "age_hours": (_utcnow() - _as_utc(oldest.created_at)).total_seconds() / 3600,
            "block": oldest.block,
            "room": oldest.room,
        }

    stale_review_count = 0
    review_cutoff = _utcnow() - timedelta(hours=settings.stale_review_hours)
    for complaint in open_complaints:
        if complaint.status in (ComplaintStatus.SUBMITTED, ComplaintStatus.AI_ANALYZED, ComplaintStatus.WARDEN_REVIEW):
            if _as_utc(complaint.created_at) < review_cutoff:
                stale_review_count += 1

    summary, highlights = _rules_summary(
        open_count=len(open_complaints),
        overdue_count=len(overdue_complaints),
        submitted_today=len(created_today),
        completed_today=len(completed_today),
        hotspots=top_hotspots,
        oldest_open=oldest_open,
        stale_review_count=stale_review_count,
        recurring_count=len(recurring),
    )

    return {
        "date": day.isoformat(),
        "submitted_today": len(created_today),
        "open_complaints": len(open_complaints),
        "overdue_complaints": len(overdue_complaints),
        "completed_complaints": len(completed_today),
        "recurring_issues": len(recurring),
        "category_counts": category_counts,
        "stale_review": stale_review_count,
        "hotspots": top_hotspots,
        "oldest_open": oldest_open,
        "summary": summary,
        "highlights": highlights,
        "generated_by": "rules",
    }
