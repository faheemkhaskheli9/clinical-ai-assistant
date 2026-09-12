"""Structured clinical extraction contract — Phase 1.

This module defines the **stable output shape** the extraction pipeline
(Phase 3, LLM function-calling) must produce and that every downstream step —
conversation summarization (Phase 3), RAG-grounded recommendations (Phase 4),
the doctor dashboard (Phase 5) — reads. The shape is finalized here in
Phase 1; Phase 3 only fills it in.

Two models make up the contract:

* :class:`ExtractionPayload` — the clinical fields an LLM is asked to fill.
  :func:`extraction_function_tool` turns it into an OpenAI-style function/tool
  definition, and its JSON Schema is exported to
  ``docs/schemas/extraction.function_tool.json`` for non-Python consumers.
* :class:`StructuredExtraction` — a persisted record: an
  :class:`ExtractionPayload` plus identity fields (``session_id``,
  ``patient_id``), server-assigned fields (``extraction_id``,
  ``extracted_at``) and the config-driven ``schema_version`` shared with
  :class:`~src.schemas.conversation.ConversationSession`.

Controlled-vocabulary fields (:class:`SymptomSeverity`, :class:`UrgencyLevel`)
are real enums, never free text, so downstream filtering and the Phase 5
urgency triage behave deterministically.

Evolving the shape: adding an *optional* field keeps ``schema_version`` at
``1.0`` (old payloads still validate under model defaults). Removing or
retyping a field is breaking — bump the ``extraction`` version in
``configs/schema.yaml`` and add a dated row to ``docs/schema-versioning.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.pii import reject_email_shaped_identifier
from src.schemas.versioning import VersionedRecord


class SymptomSeverity(str, Enum):
    """Controlled severity for a reported symptom. Absent => the patient did not say."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class UrgencyLevel(str, Enum):
    """Overall triage urgency for the encounter.

    Maps to Phase 5 doctor-dashboard behaviour: ``ROUTINE`` sits in the normal
    queue, ``URGENT`` is surfaced above routine items, ``EMERGENT`` triggers a
    prominent flag. Kept deliberately small; widen only via a schema bump.
    """

    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENT = "emergent"


class Symptom(BaseModel):
    """One reported symptom.

    ``name`` is required; ``onset`` and ``severity`` are optional because a
    patient often mentions a symptom without either. A bare string is accepted
    and coerced to ``{"name": <string>}`` so the pre-structured
    ``["cough", "fever"]`` payload shape still validates unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, description="Symptom in the patient's words, lightly normalized"
    )
    onset: str | None = Field(
        default=None,
        description="When/how it began, free text (e.g. '3 days ago', 'gradual over weeks')",
    )
    severity: SymptomSeverity | None = Field(
        default=None, description="Controlled severity; None when the patient did not say"
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_bare_string(cls, data: Any) -> Any:
        """Accept ``"cough"`` as shorthand for ``{"name": "cough"}``."""
        if isinstance(data, str):
            return {"name": data}
        return data

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("symptom name must not be blank")
        return stripped


class Vitals(BaseModel):
    """Vital signs, all optional — a conversation rarely mentions every one.

    Every field carries a physiologically-plausible range, not just the ones
    where a negative is obviously wrong. The bounds are wide enough that any
    real reading passes; a value outside them means the extractor mis-parsed
    (e.g. ``temperature_c=-98.6`` from the text "98.6", or a decimal point
    dropped). Per the repo robustness rules, rejecting that loudly beats
    storing a bad vital that then flows into clinical reasoning as fact.
    """

    model_config = ConfigDict(extra="forbid")

    systolic_bp: int | None = Field(default=None, ge=0, le=400, description="mmHg")
    diastolic_bp: int | None = Field(default=None, ge=0, le=300, description="mmHg")
    heart_rate: int | None = Field(
        default=None, ge=0, le=500, description="beats per minute"
    )
    temperature_c: float | None = Field(
        default=None, ge=20.0, le=45.0, description="degrees Celsius"
    )
    respiratory_rate: int | None = Field(
        default=None, ge=0, le=200, description="breaths per minute"
    )
    oxygen_saturation: int | None = Field(
        default=None, ge=0, le=100, description="SpO2, percent"
    )


class ExtractionPayload(BaseModel):
    """The clinical fields an LLM fills during function-calling extraction.

    Everything is optional: a short conversation may support only a chief
    complaint. Populate a field only when the conversation states it —
    downstream steps treat absence as "not mentioned", never as "denied".
    """

    model_config = ConfigDict(extra="forbid")

    chief_complaint: str | None = Field(
        default=None, description="Primary reason for the visit, in the patient's words"
    )
    symptoms: list[Symptom] = Field(
        default_factory=list,
        description="Reported symptoms, each with a name and optional onset/severity",
    )
    vitals: Vitals = Field(default_factory=Vitals, description="Any vitals mentioned")
    medical_history: list[str] = Field(
        default_factory=list, description="Past conditions, procedures, family history"
    )
    medications: list[str] = Field(default_factory=list, description="Current medications")
    allergies: list[str] = Field(default_factory=list, description="Known allergies")
    urgency: UrgencyLevel | None = Field(
        default=None,
        description="Overall triage urgency if the conversation supports one; None if unclear",
    )


class StructuredExtraction(ExtractionPayload, VersionedRecord):
    """A persisted structured-extraction record for one intake conversation.

    ``schema_version`` is inherited from :class:`VersionedRecord`; unset on
    creation it is stamped from ``configs/schema.yaml``, and an explicit value
    the config does not list as supported is rejected at parse time.
    """

    SCHEMA_NAME = "extraction"

    model_config = ConfigDict(extra="forbid")

    extraction_id: UUID = Field(
        default_factory=uuid4, description="Unique id for this extraction"
    )
    session_id: UUID = Field(
        ..., description="ConversationSession this record was extracted from"
    )
    patient_id: str = Field(
        ...,
        min_length=1,
        description="Pseudonymous patient identifier (never a real name, email, or SSN)",
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp the extraction was produced",
    )

    @field_validator("patient_id")
    @classmethod
    def patient_id_must_be_pseudonymous(cls, value: str) -> str:
        return reject_email_shaped_identifier(value)


_EXTRACTION_TOOL_NAME = "record_structured_extraction"
_EXTRACTION_TOOL_DESCRIPTION = (
    "Record the structured clinical information stated in a patient intake "
    "conversation. Include a field only when the conversation supports it; omit "
    "anything the patient did not mention. Do not infer, guess, or diagnose."
)


def extraction_function_tool(*, name: str = _EXTRACTION_TOOL_NAME) -> dict[str, Any]:
    """Return an OpenAI-style ``{"type": "function", ...}`` tool definition.

    The ``parameters`` are :class:`ExtractionPayload`'s JSON Schema — the
    identity/server fields on :class:`StructuredExtraction` (``session_id``,
    ``patient_id``, ``extraction_id``, ``extracted_at``, ``schema_version``)
    are supplied by the application, not the model, so they are deliberately
    absent here.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": _EXTRACTION_TOOL_DESCRIPTION,
            "parameters": ExtractionPayload.model_json_schema(),
        },
    }
