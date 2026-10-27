"""HostelDesk FastAPI application entry point."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routes import alerts, auth, complaints, digest, tasks, warden

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
)
logger = logging.getLogger("hosteldesk")

app = FastAPI(
    title="HostelDesk API",
    description=(
        "AI-assisted hostel complaint and task desk. "
        "Central product rule: **AI suggests; the Warden decides.**"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)

app.include_router(warden.router)
app.include_router(auth.router)
app.include_router(auth.role_router)
app.include_router(complaints.router)
app.include_router(tasks.router)
app.include_router(alerts.router)
app.include_router(digest.router)


@app.get("/health", summary="Health check (includes DB connectivity)")
def health() -> JSONResponse:
    """Cheap one-query database check; still fast and side-effect free."""
    from sqlalchemy import text

    from app.db.database import SessionLocal

    database_status = "unreachable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        database_status = "connected"
        status_code = status.HTTP_200_OK
    except Exception as exc:  # noqa: BLE001 - health must never crash
        logger.error("Database health check failed: %s", exc)
    finally:
        session.close()

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "degraded",
            "database": database_status,
        },
    )


@app.get("/health/ai", summary="AI service health (configuration only, no API call)")
def health_ai() -> dict[str, object]:
    """Reports Gemini configuration without calling the API or exposing secrets.

    Safe to poll: no network request, no API key, no database URL in the body.
    """
    return {
        "provider": "gemini",
        "model": settings.gemini_model,
        "fallback_model": settings.gemini_fallback_model,
        "configured": bool(settings.gemini_api_key),
        "timeout_seconds": settings.ai_request_timeout_seconds,
        "max_output_tokens": settings.gemini_max_output_tokens,
        "thinking_budget": 0 if settings.gemini_model.lower().startswith("gemini-2.5") else None,
        "duplicate_check": True,
    }


@app.get("/", summary="API welcome message")
def root() -> dict[str, str]:
    return {"message": "HostelDesk API - AI-assisted hostel complaint and task desk"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Trim validation payloads and keep credentials out of error responses."""
    errors = exc.errors()
    cleaned = []
    for error in errors:
        location = {str(part).lower() for part in error.get("loc", [])}
        if "photo" in location or "password" in location:
            error.pop("input", None)
        cleaned.append(error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(cleaned)},
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )
