"""Tests for config-driven schema versioning (src/schemas/versioning.py)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas import versioning
from src.schemas.conversation import ConversationSession
from src.schemas.versioning import (
    BUILTIN_DEFAULTS,
    CompatibilityStatus,
    IncompatibleSchemaVersionError,
    SchemaRegistry,
    check_version,
    classify_version,
    current_version,
    load_registry,
    reload_registry,
    supported_versions,
)


@pytest.fixture(autouse=True)
def _clean_registry_cache():
    """Every test starts and ends with a cold registry cache."""
    reload_registry()
    yield
    reload_registry()


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "schema.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _use_config(monkeypatch, path: Path) -> None:
    monkeypatch.setenv(versioning.ENV_VAR, str(path))
    reload_registry()


# --- shipped default config -------------------------------------------------


def test_shipped_config_reports_version_1_0():
    assert current_version("conversation") == "1.0"
    assert current_version("extraction") == "1.0"
    assert supported_versions("conversation") == ("1.0",)


def test_unknown_schema_name_raises_keyerror():
    with pytest.raises(KeyError):
        current_version("not_a_schema")


# --- missing-file behaviour (robustness rule 7) ---------------------------


def test_missing_default_config_falls_back_to_builtin_defaults(monkeypatch):
    monkeypatch.setattr(versioning, "DEFAULT_CONFIG_PATH", Path("does-not-exist.yaml"))
    monkeypatch.delenv(versioning.ENV_VAR, raising=False)
    reload_registry()

    registry = load_registry()
    assert registry.conversation.current == BUILTIN_DEFAULTS["conversation"]["current"]


def test_explicitly_named_missing_config_is_a_hard_error(monkeypatch, tmp_path):
    missing = tmp_path / "nope.yaml"
    monkeypatch.setenv(versioning.ENV_VAR, str(missing))
    reload_registry()

    with pytest.raises(FileNotFoundError):
        load_registry()


# --- config drives the value, it is not hardcoded ------------------------


def test_config_change_moves_the_stamped_version(monkeypatch, tmp_path):
    path = _write_config(
        tmp_path,
        """
        conversation:
          current: "2.0"
          supported: ["1.0", "2.0"]
        extraction:
          current: "1.0"
          supported: ["1.0"]
        compatibility:
          on_unknown_version: "error"
        """,
    )
    _use_config(monkeypatch, path)

    assert current_version("conversation") == "2.0"
    assert ConversationSession(patient_id="patient-pseudo-1").schema_version == "2.0"


def test_registry_rejects_current_not_in_supported():
    with pytest.raises(ValidationError):
        SchemaRegistry.model_validate(
            {
                "conversation": {"current": "9.9", "supported": ["1.0"]},
                "extraction": {"current": "1.0", "supported": ["1.0"]},
            }
        )


# --- compatibility classification ---------------------------------------


def test_classify_version_buckets(monkeypatch, tmp_path):
    path = _write_config(
        tmp_path,
        """
        conversation:
          current: "2.0"
          supported: ["1.0", "2.0"]
        extraction:
          current: "1.0"
          supported: ["1.0"]
        compatibility:
          on_unknown_version: "error"
        """,
    )
    _use_config(monkeypatch, path)

    assert classify_version("conversation", "2.0") is CompatibilityStatus.CURRENT
    assert classify_version("conversation", "1.0") is CompatibilityStatus.OLDER_SUPPORTED
    assert classify_version("conversation", "3.0") is CompatibilityStatus.UNKNOWN


def test_check_version_error_policy_raises_on_unknown():
    with pytest.raises(IncompatibleSchemaVersionError):
        check_version("conversation", "0.1")


def test_check_version_warn_policy_warns_on_unknown(monkeypatch, tmp_path):
    path = _write_config(
        tmp_path,
        """
        conversation:
          current: "1.0"
          supported: ["1.0"]
        extraction:
          current: "1.0"
          supported: ["1.0"]
        compatibility:
          on_unknown_version: "warn"
        """,
    )
    _use_config(monkeypatch, path)

    with pytest.warns(UserWarning):
        status = check_version("conversation", "0.1")
    assert status is CompatibilityStatus.UNKNOWN


def test_check_version_strict_override_beats_config():
    # config policy is "error" here, but strict=False downgrades to a warning
    with pytest.warns(UserWarning):
        check_version("conversation", "0.1", strict=False)
