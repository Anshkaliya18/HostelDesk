"""Application settings loaded from environment variables (backend/.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Database ----
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/hosteldesk"
    migration_database_url: str = ""
    application_db_role: str = "hosteldesk_app"

    # ---- Supabase (server-side only; never exposed to the frontend) ----
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_publishable_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SUPABASE_PUBLISHABLE_KEY", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"
        ),
    )
    supabase_storage_bucket: str = "complaint-photos"
    signed_url_expiry_seconds: int = 3600

    # ---- Gemini ----
    gemini_api_key: str = ""
    # Default: Gemini 2.5 Flash (fallback: 2.5 Flash-Lite) through the Google
    # Generative Language API. Gemma 4 is a single env-var swap once Google
    # API keys expose it (e.g. GEMINI_MODEL=gemma-4-31b-it).
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash-lite"
    # Short timeout: classification is a small JSON task. If the model
    # doesn't answer within this, AI is marked failed and the complaint stays
    # in WARDEN_REVIEW for manual review. Configurable per deployment.
    ai_request_timeout_seconds: int = 10
    # Compact structured reply only; no chain-of-thought stored or logged.
    gemini_max_output_tokens: int = 512
    # Maximum image bytes sent to Gemini. Larger images are downsized (if
    # Pillow is available) before the model request.
    max_ai_image_mb: float = 1.0

    @property
    def max_ai_image_bytes(self) -> int:
        return int(self.max_ai_image_mb * 1024 * 1024)

    # ---- CORS ----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- Staff signup ----
    # STAFF_INVITE_CODE gates Warden/Worker signup. When empty, staff signup is
    # disabled entirely (403). Student signup stays open.
    staff_invite_code: str = ""

    # ---- Abuse limits (in-memory sliding window; per process) ----
    complaint_rate_limit_10min: int = 5
    complaint_rate_limit_daily: int = 20
    signup_rate_limit_hourly: int = 10

    # ---- Rules ----
    task_overdue_hours: int = 24
    # Severity-based SLA (falls back to task_overdue_hours when unset).
    task_overdue_hours_high: int = 4
    task_overdue_hours_medium: int = 24
    task_overdue_hours_low: int = 72
    # Complaints waiting for warden review longer than this count as stale in
    # the daily digest.
    stale_review_hours: int = 4
    # Optional digest polish with one Gemini text call (rules output is the
    # always-on baseline). Counters only - never student names or photos.
    digest_ai_polish: bool = True
    repeat_problem_window_days: int = 7
    repeat_problem_threshold: int = 3

    # ---- Uploads ----
    max_image_size_mb: float = 5.0
    upload_dir: Path = BASE_DIR / "uploads"

    @property
    def supabase_configured(self) -> bool:
        """True when a Supabase project is configured for Storage."""
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def supabase_auth_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def alembic_database_url(self) -> str:
        """Prefer an owner-level URL for schema changes; runtime keeps DATABASE_URL."""
        return self.migration_database_url or self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_image_size_bytes(self) -> int:
        return int(self.max_image_size_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
