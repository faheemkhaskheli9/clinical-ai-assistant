from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.schemas.conversation import ConversationSession, ConversationTurn, TurnRole
from src.schemas.versioning import current_version, reload_registry

NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_registry_cache():
    reload_registry()
    yield
    reload_registry()


def _valid_session_payload() -> dict:
    return {
        "patient_id": "patient-pseudo-0001",
        "turns": [
            {
                "role": "system",
                "content": "Intake session started.",
                "timestamp": NOW.isoformat(),
            },
            {
                "role": "assistant",
                "content": "What brings you in today?",
                "timestamp": (NOW + timedelta(seconds=1)).isoformat(),
            },
            {
                "role": "patient",
                "content": "I've had a headache for two days.",
                "timestamp": (NOW + timedelta(seconds=30)).isoformat(),
            },
        ],
        "metadata": {"channel": "web-chat", "locale": "en-US"},
    }


def test_valid_conversation_session_payload_parses():
    session = ConversationSession.model_validate(_valid_session_payload())

    assert session.schema_version == "1.0"
    assert session.patient_id == "patient-pseudo-0001"
    assert len(session.turns) == 3
    assert session.turns[0].role == TurnRole.SYSTEM
    assert session.turns[-1].role == TurnRole.PATIENT
    assert session.session_id is not None


def test_default_session_has_no_turns_and_a_generated_id():
    session = ConversationSession(patient_id="patient-pseudo-0002")

    assert session.turns == []
    assert session.session_id is not None
    assert session.created_at.tzinfo is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("patient_id"),
        lambda payload: payload["turns"].__setitem__(0, {**payload["turns"][0], "role": "nurse"}),
        lambda payload: payload["turns"].__setitem__(0, {**payload["turns"][0], "content": ""}),
        lambda payload: payload.update(unexpected_field="not allowed"),
    ],
)
def test_malformed_conversation_session_payload_fails_validation(mutate):
    payload = _valid_session_payload()
    mutate(payload)

    with pytest.raises(ValidationError):
        ConversationSession.model_validate(payload)


def test_patient_id_rejects_email_shaped_values():
    payload = _valid_session_payload()
    payload["patient_id"] = "patient@example.com"

    with pytest.raises(ValidationError):
        ConversationSession.model_validate(payload)


def test_turns_must_be_chronological():
    payload = _valid_session_payload()
    payload["turns"][0], payload["turns"][1] = payload["turns"][1], payload["turns"][0]

    with pytest.raises(ValidationError):
        ConversationSession.model_validate(payload)


def test_conversation_turn_requires_non_empty_content():
    with pytest.raises(ValidationError):
        ConversationTurn(role="patient", content="")


def test_schema_version_defaults_from_config():
    session = ConversationSession(patient_id="patient-pseudo-0003")
    assert session.schema_version == current_version("conversation")


def test_explicit_unsupported_schema_version_is_rejected():
    payload = _valid_session_payload()
    payload["schema_version"] = "0.0"
    with pytest.raises(ValidationError):
        ConversationSession.model_validate(payload)


def test_conversation_module_has_no_eager_version_constant():
    """Importing the module must not read configs/schema.yaml at import time.

    A module-level ``SCHEMA_VERSION`` computed at import turned a malformed
    config into an unimportable ``src.schemas`` package (for code that never
    touches versioning) and captured a value ``reload_registry()`` could not
    update. The version is resolved lazily by ``VersionedRecord`` instead.
    """
    import src.schemas.conversation as module

    assert not hasattr(module, "SCHEMA_VERSION")
