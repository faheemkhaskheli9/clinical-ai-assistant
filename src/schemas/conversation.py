"""Shared conversation schema for patient intake sessions.

This is the single authoritative message format used by the chat intake flow,
the extraction pipeline, and storage. Any component that reads or writes a
conversation session should import these models rather than redefining the
shape ad hoc.

Schema versioning is config-driven: :class:`ConversationSession` inherits
``schema_version`` from :class:`src.schemas.versioning.VersionedRecord`, whose
default value comes from ``configs/schema.yaml`` (key ``conversation``) read
at startup. To evolve the shape, edit that file and add a migration note to
``docs/schema-versioning.md`` — do not hardcode a version constant here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.pii import reject_email_shaped_identifier
from src.schemas.versioning import VersionedRecord, current_version

# Convenience alias for "the conversation version this process started with",
# resolved from configs/schema.yaml at import time (not a hardcoded literal).
SCHEMA_VERSION: str = current_version("conversation")


class TurnRole(str, Enum):
    """Who produced a given conversation turn."""

    PATIENT = "patient"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationTurn(BaseModel):
    """A single message within a patient intake conversation."""

    model_config = ConfigDict(extra="forbid")

    turn_id: UUID = Field(default_factory=uuid4, description="Unique id for this turn")
    role: TurnRole = Field(..., description="Who produced this turn")
    content: str = Field(..., min_length=1, description="Free-text turn content")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp the turn was recorded",
    )


class ConversationSession(VersionedRecord):
    """A full patient intake conversation: session metadata plus its turns.

    ``schema_version`` is inherited from :class:`VersionedRecord`; unset on
    creation it is stamped from ``configs/schema.yaml``, and an explicit value
    that the config does not list as supported is rejected at parse time.
    """

    SCHEMA_NAME = "conversation"

    model_config = ConfigDict(extra="forbid")

    session_id: UUID = Field(default_factory=uuid4, description="Unique id for this session")
    patient_id: str = Field(
        ...,
        min_length=1,
        description="Pseudonymous patient identifier (never a real name, email, or SSN)",
    )
    turns: list[ConversationTurn] = Field(
        default_factory=list, description="Ordered conversation turns, oldest first"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp the session was created",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Free-form session metadata, e.g. intake channel, locale",
    )

    @field_validator("patient_id")
    @classmethod
    def patient_id_must_be_pseudonymous(cls, value: str) -> str:
        """Reject the most obvious accidental-PII shapes (defense in depth only).

        Real de-identification happens upstream, before an id reaches this
        schema; this just catches passing a raw email as the identifier.
        """
        return reject_email_shaped_identifier(value)

    @field_validator("turns")
    @classmethod
    def turns_must_be_chronological(cls, value: list[ConversationTurn]) -> list[ConversationTurn]:
        for previous, current in zip(value, value[1:]):
            if current.timestamp < previous.timestamp:
                raise ValueError("turns must be in non-decreasing timestamp order")
        return value
