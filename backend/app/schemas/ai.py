"""Pydantic schemas for the AI orchestration service.

These enums mirror the database enums but live here so that Gemini output is
strictly validated before anything touches the database.
"""

import enum

from pydantic import BaseModel, field_validator


class ComplaintCategory(enum.StrEnum):
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    CLEANING = "CLEANING"
    FURNITURE = "FURNITURE"


class Severity(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SuggestedWorker(enum.StrEnum):
    ELECTRICIAN = "ELECTRICIAN"
    PLUMBER = "PLUMBER"
    CLEANER = "CLEANER"
    CARPENTER = "CARPENTER"


class Confidence(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def _max_20_words(value: object) -> object:
    """Keep the AI reason short and readable (maximum 20 words)."""
    if isinstance(value, str):
        words = value.strip().split()
        if len(words) > 20:
            return " ".join(words[:20])
        return value.strip() or None
    return value


class AIAnalysisResult(BaseModel):
    """Strictly validated Gemini output.

    ``category``/``severity``/``suggested_worker`` are mandatory; the richer
    ``reason``/``confidence``/``safety_flag``/``duplicate_of_complaint_id``
    fields are optional so a terse model reply still validates. Provenance is
    recorded from ``model`` set by the caller, though the model may include it.
    """

    category: ComplaintCategory
    severity: Severity
    suggested_worker: SuggestedWorker
    reason: str | None = None
    confidence: Confidence | None = None
    safety_flag: bool = False
    duplicate_of_complaint_id: int | None = None
    model: str | None = None

    @field_validator("category", "severity", "suggested_worker", "confidence", mode="before")
    @classmethod
    def uppercase_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def limit_reason(cls, value: object) -> object:
        return _max_20_words(value)
