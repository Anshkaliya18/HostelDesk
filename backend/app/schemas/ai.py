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


class AIAnalysisResult(BaseModel):
    """Strictly validated Gemini output."""

    category: ComplaintCategory
    severity: Severity
    suggested_worker: SuggestedWorker

    @field_validator("*", mode="before")
    @classmethod
    def uppercase_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value
