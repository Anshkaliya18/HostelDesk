"""AI orchestration service (Gemini) — async.

Keeps the entire Gemini integration isolated in this module. Takes the
complaint photo + description, asks Gemma 4 via the Gemini API for a
structured JSON classification, and validates the reply with Pydantic.

All network I/O is async (httpx.AsyncClient) so the FastAPI background
task never blocks the main event loop.

Student-facing request flow (POST /complaints):
    validate → save complaint (COMMIT) → return HTTP 201 immediately
    → background Gemma 4 analysis → save recommendation → WARDEN_REVIEW

The student never waits for Gemini, retries, fallback, JSON parsing, or DB.
"""

import asyncio
import base64
import io
import json
import logging
import time
from typing import Any

import httpx
from app.core.config import settings
from app.schemas.ai import AIAnalysisResult

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

PROMPT_TEMPLATE = """You are HostelDesk's hostel maintenance classifier.
Classify a hostel maintenance problem from ONE photo and a student description
(English, Hindi, or Hinglish).

Reply with ONLY this JSON object, no markdown, no explanation:
{{"category": "ELECTRICAL|PLUMBING|CLEANING|FURNITURE",
  "severity": "LOW|MEDIUM|HIGH",
  "suggested_worker": "ELECTRICIAN|PLUMBER|CLEANER|CARPENTER"}}

Rules:
- Use only the listed values.
- Estimate severity from safety risk and impact.
- Suggest a worker TYPE, never an individual person.
- Base everything only on the photo and description; never invent problems.
- The warden makes the final assignment; you only recommend.

Description: {description}
"""

# Tight retry policy for hackathon MVP: one attempt + one retry per model,
# then fallback once. Maximum 4 total Gemini requests per complaint.
# Only throttle/unavailability statuses are retried; 4xx moves straight to
# the fallback model.
RETRYABLE_STATUS_CODES = {429, 503}
MAX_RETRIES_PER_MODEL = 1
BACKOFF_SECONDS = 2


class AIUnavailableResult:
    """Not a Pydantic model; represents a safe 'analysis failed' outcome."""

    def __init__(self, raw_response: dict[str, Any]) -> None:
        self.raw_response = raw_response
        self.ok = False


def build_prompt(description: str) -> str:
    return PROMPT_TEMPLATE.format(description=description)


def _model_chain() -> list[str]:
    """Primary then fallback Gemma models, via configuration (never hard-coded)."""
    models = [settings.gemini_model, settings.gemini_fallback_model]
    unique: list[str] = []
    for model in models:
        if model and model not in unique:
            unique.append(model)
    return unique


def _extract_answer_text(parts: list[dict[str, Any]]) -> str | None:
    """Return the final answer text from a candidate.

    Thinking-class models (Gemma 4) emit chain-of-thought parts flagged with
    'thought': True before the real answer. Reading part[0] would grab the
    thoughts; the answer is the last non-thought part. Chain-of-thought is
    never logged or stored.
    """
    for part in reversed(parts):
        if isinstance(part, dict) and not part.get("thought") and "text" in part:
            return part["text"]
    return None


def _resize_image_if_needed(image: bytes, mime: str) -> tuple[bytes, str]:
    """Downsize an image if it exceeds the configured max AI image size.

    Returns (possibly_resized_bytes, mime). If Pillow is unavailable or
    resizing fails, returns the original image unchanged. The image is
    prepared exactly once.
    """
    if len(image) <= settings.max_ai_image_bytes:
        return image, mime

    try:
        from PIL import Image  # type: ignore[import-not-found]

        img = Image.open(io.BytesIO(image))
        max_edge = 1024  # ample for maintenance classification
        if max(img.width, img.height) > max_edge:
            img.thumbnail((max_edge, max_edge))
            buffer = io.BytesIO()
            fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(
                mime, "JPEG"
            )
            save_kwargs: dict[str, Any] = {}
            if fmt == "JPEG":
                save_kwargs["quality"] = 85
            img.save(buffer, format=fmt, **save_kwargs)
            resized = buffer.getvalue()
            logger.info(
                "[AI] image resized %d -> %d bytes for model request",
                len(image),
                len(resized),
            )
            return resized, mime
    except Exception as exc:  # noqa: BLE001 - resizing is best-effort
        logger.warning("[AI] image resize skipped: %s", exc)

    return image, mime


async def _post_generate_async(
    client: httpx.AsyncClient, model: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Single request for ONE model with at most one bounded retry.

    Returns the parsed Gemini body dict, or None after exhausting retries
    for transient statuses. Never raises; all errors are logged (no secrets).
    """
    url = f"{GEMINI_API_BASE_URL}/models/{model}:generateContent"
    headers = {"x-goog-api-key": settings.gemini_api_key}

    for attempt in range(MAX_RETRIES_PER_MODEL + 1):
        started = time.perf_counter()
        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=settings.ai_request_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            # Transport-level failure (timeout, DNS, TLS...). Move on to the
            # next model instead of retrying a dead route.
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "[AI] request to %s failed after %.0fms: %s", model, duration_ms, exc
            )
            return None

        duration_ms = (time.perf_counter() - started) * 1000

        if response.status_code < 400:
            try:
                body = response.json()
            except ValueError as exc:
                logger.error(
                    "[AI] Gemini (%s) non-JSON body after %.0fms: %s",
                    model,
                    duration_ms,
                    exc,
                )
                return None
            logger.info(
                "[AI] Gemini response received model=%s duration_ms=%.0f status=%s",
                model,
                duration_ms,
                response.status_code,
            )
            return body

        # Error status: log the exact API message (message only, no secrets).
        try:
            api_message = str(response.json().get("error", {}).get("message", ""))[:200]
        except ValueError:
            api_message = response.text[:200]
        logger.error(
            "[AI] Gemini (%s) HTTP %s after %.0fms: %s",
            model,
            response.status_code,
            duration_ms,
            api_message,
        )

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES_PER_MODEL:
            logger.warning(
                "[AI] Gemma %s transient HTTP %s; retry %d/%d in %ds",
                model,
                response.status_code,
                attempt + 1,
                MAX_RETRIES_PER_MODEL,
                BACKOFF_SECONDS,
            )
            await asyncio.sleep(BACKOFF_SECONDS)
            continue

        return None  # non-retryable, or retries exhausted

    return None  # pragma: no cover - loop always returns inside


async def _request_model_async(
    client: httpx.AsyncClient,
    model: str,
    image: bytes | None,
    image_mime: str | None,
    description: str,
) -> dict[str, Any] | None:
    """Analyze with ONE model. Returns validated dict, or error dict."""
    parts: list[dict[str, Any]] = [{"text": build_prompt(description)}]
    if image:
        # Validate/sanitize MIME; never blindly assume image/jpeg.
        mime = image_mime or "image/jpeg"
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            logger.warning(
                "[AI] unsupported image mime %s for model %s, treating as jpeg",
                mime,
                model,
            )
            mime = "image/jpeg"
        image, mime = _resize_image_if_needed(image, mime)
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(image).decode("ascii"),
                }
            }
        )

    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": settings.gemini_max_output_tokens,
            "responseMimeType": "application/json",
        },
    }

    started = time.perf_counter()
    body = await _post_generate_async(client, model, payload)
    if body is None:
        return {"error": "gemini_request_failed", "model": model}

    candidate = body.get("candidates") or [{}]
    content_parts = (candidate[0].get("content") or {}).get("parts") or []
    text = _extract_answer_text(content_parts)
    if text is None:
        shape = str(body)[:400]
        logger.error("Unexpected Gemini (%s) response shape: %s", model, shape)
        return {"error": "gemini_unexpected_response", "raw": shape, "model": model}

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Gemini (%s) reply is not valid JSON: %s", model, exc)
        return {"error": "gemini_bad_json", "raw": text[:400], "model": model}

    if isinstance(parsed, dict):
        parsed["model"] = model
    else:
        return {"error": "gemini_bad_json", "raw": text[:400], "model": model}

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "[AI] JSON parsed model=%s duration_ms=%.0f category=%s severity=%s worker=%s",
        model,
        duration_ms,
        parsed.get("category"),
        parsed.get("severity"),
        parsed.get("suggested_worker"),
    )
    return parsed


async def _call_gemini_async(
    image: bytes | None, image_mime: str | None, description: str
) -> dict[str, Any] | None:
    """Analyze with the primary Gemma model, falling back to the configured
    fallback Gemma model. Returns parsed json (with 'model' provenance) or
    an error dict when every model failed. Never raises; never fabricates."""
    if not settings.gemini_api_key:
        logger.warning("AI analysis skipped: GEMINI_API_KEY is not configured.")
        return {"error": "gemini_not_configured"}

    models = _model_chain()
    aggregated: list[str] = []
    async with httpx.AsyncClient() as client:
        for model in models:
            started = time.perf_counter()
            result = await _request_model_async(
                client, model, image, image_mime, description
            )
            duration_ms = (time.perf_counter() - started) * 1000
            if result is not None and "error" in result and "model" in result:
                aggregated.append(f"{result['model']}: {result['error']}")
                logger.warning(
                    "[AI] model %s failed in %.0fms: %s",
                    model,
                    duration_ms,
                    result["error"],
                )
                continue
            if result is None:
                aggregated.append(f"{model}: gemini_request_failed")
                logger.warning("[AI] model %s request failed in %.0fms", model, duration_ms)
                continue
            logger.info("[AI] Gemma model used: %s (%.0fms)", model, duration_ms)
            return result

    logger.error("All configured Gemma models failed: %s", "; ".join(aggregated))
    return {"error": "gemini_unavailable", "raw": "; ".join(aggregated)[:400]}


async def analyze_complaint(
    image: bytes | None, image_mime: str | None, description: str
) -> AIAnalysisResult | AIUnavailableResult:
    """Public entry point. Never raises.

    Calls Gemma 4 through the Gemini API exactly once per complaint
    (primary + bounded retry + fallback), validates the structured JSON,
    and returns either a valid AIAnalysisResult or a safe failure result.
    """
    started = time.perf_counter()
    try:
        parsed = await _call_gemini_async(image, image_mime, description)
        if parsed is None or "error" in parsed:
            return AIUnavailableResult(parsed or {"error": "gemini_empty_response"})

        analysis = AIAnalysisResult.model_validate(parsed)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "[AI] analysis ok: model=%s category=%s severity=%s worker=%s duration_ms=%.0f",
            parsed.get("model"),
            analysis.category.value,
            analysis.severity.value,
            analysis.suggested_worker.value,
            duration_ms,
        )
        return analysis

    except Exception:  # noqa: BLE001 - the API must never crash on AI problems
        duration_ms = (time.perf_counter() - started) * 1000
        logger.exception("[AI] analysis failed unexpectedly after %.0fms", duration_ms)
        return AIUnavailableResult({"error": "ai_analysis_failed"})
