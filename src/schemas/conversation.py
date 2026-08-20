"""Shared conversation schema for patient intake sessions.

This is the single authoritative message format used by the chat intake flow,
the extraction pipeline, and storage. Any component that reads or writes a
conversation session should import these models rather than redefining the
shape ad hoc.

Schema versioning: bump ``SCHEMA_VERSION`` (and add a new ``Literal`` value to
``ConversationSession.schema_version``) whenever a breaking change is made to
the session or turn shape, so older persisted records can still be
distinguished from newer ones.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"


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


class ConversationSession(BaseModel):
    """A full patient intake conversation: session metadata plus its turns."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(
        default=SCHEMA_VERSION,
        description="Version of this schema the record was written with",
    )
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

        This is not a PII detector — real de-identification happens upstream,
        before an id ever reaches this schema. It just catches the easy
        mistake of passing a raw email address as the patient identifier.
        """
        if "@" in value:
            raise ValueError("patient_id must be a pseudonymous identifier, not an email address")
        return value

    @field_validator("turns")
    @classmethod
    def turns_must_be_chronological(cls, value: list[ConversationTurn]) -> list[ConversationTurn]:
        for previous, current in zip(value, value[1:]):
            if current.timestamp < previous.timestamp:
                raise ValueError("turns must be in non-decreasing timestamp order")
        return value
