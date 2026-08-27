"""Structured clinical extraction record — Phase 1 contract stub.

The full field contract for what the extraction pipeline pulls out of a
conversation is finalized in Phase 3 (LLM function-calling extraction). This
module exists from Phase 1 so that every stored extraction record already
carries the same config-driven ``schema_version`` as a
:class:`~src.schemas.conversation.ConversationSession` — the versioning
mechanism (:mod:`src.schemas.versioning`) is identical for both record types.

Fields here are intentionally minimal. Adding optional siblings in Phase 3 is
a backward-compatible change and keeps ``schema_version`` at ``1.0``; removing
or retyping a field is breaking and must bump the ``extraction`` version in
``configs/schema.yaml`` with a note in ``docs/schema-versioning.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.pii import reject_email_shaped_identifier
from src.schemas.versioning import VersionedRecord


class Vitals(BaseModel):
    """Vital signs, all optional — a conversation rarely mentions every one."""

    model_config = ConfigDict(extra="forbid")

    systolic_bp: int | None = Field(default=None, ge=0, description="mmHg")
    diastolic_bp: int | None = Field(default=None, ge=0, description="mmHg")
    heart_rate: int | None = Field(default=None, ge=0, description="beats per minute")
    temperature_c: float | None = Field(default=None, description="degrees Celsius")
    respiratory_rate: int | None = Field(default=None, ge=0, description="breaths per minute")
    oxygen_saturation: int | None = Field(
        default=None, ge=0, le=100, description="SpO2, percent"
    )


class StructuredExtraction(VersionedRecord):
    """Structured fields extracted from one patient intake conversation."""

    SCHEMA_NAME = "extraction"

    model_config = ConfigDict(extra="forbid")

    extraction_id: UUID = Field(default_factory=uuid4, description="Unique id for this extraction")
    session_id: UUID = Field(
        ..., description="ConversationSession this record was extracted from"
    )
    patient_id: str = Field(
        ...,
        min_length=1,
        description="Pseudonymous patient identifier (never a real name, email, or SSN)",
    )
    chief_complaint: str | None = Field(
        default=None, description="Primary reason for the visit, in the patient's words"
    )
    symptoms: list[str] = Field(default_factory=list, description="Reported symptoms")
    vitals: Vitals = Field(default_factory=Vitals, description="Any vitals mentioned")
    medical_history: list[str] = Field(
        default_factory=list, description="Past conditions, procedures, family history"
    )
    medications: list[str] = Field(default_factory=list, description="Current medications")
    allergies: list[str] = Field(default_factory=list, description="Known allergies")
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp the extraction was produced",
    )

    @field_validator("patient_id")
    @classmethod
    def patient_id_must_be_pseudonymous(cls, value: str) -> str:
        return reject_email_shaped_identifier(value)
