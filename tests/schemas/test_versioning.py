"""Tests for config-driven schema versioning (src/schemas/versioning.py)."""

from __future__ import annotations

import logging
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
    assert (
        registry.spec("conversation").current
        == BUILTIN_DEFAULTS["conversation"]["current"]
    )


def test_builtin_defaults_match_shipped_config():
    """BUILTIN_DEFAULTS must not drift from configs/schema.yaml (finding 5).

    A "keep in sync" comment is not enforcement; this asserts the two produce
    an identical validated registry, so any edit to one without the other
    fails CI instead of shipping two behaviours across environments.
    """
    shipped = SchemaRegistry.model_validate(
        versioning._read_yaml_mapping(versioning.DEFAULT_CONFIG_PATH)
    )
    builtin = SchemaRegistry.model_validate(BUILTIN_DEFAULTS)
    assert builtin.model_dump() == shipped.model_dump()


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


def test_env_var_set_after_first_load_is_honoured(monkeypatch, tmp_path):
    """A config source chosen after the first lookup must not be ignored (finding 1).

    The old code @lru_cache'd on the ``path`` arg only, so a ``path=None`` call
    cached whatever ``$CLINICAL_AI_SCHEMA_CONFIG`` / the filesystem said at that
    moment; a later env var was silently dropped (repo CLAUDE.md rule 7).
    """
    monkeypatch.delenv(versioning.ENV_VAR, raising=False)
    reload_registry()
    # First use — caches the default/builtin registry under the resolved key.
    assert current_version("conversation") == "1.0"

    path = _write_config(
        tmp_path,
        """
        conversation:
          current: "2.0"
          supported: ["1.0", "2.0"]
        extraction:
          current: "1.0"
          supported: ["1.0"]
        """,
    )
    monkeypatch.setenv(versioning.ENV_VAR, str(path))
    # No reload_registry() — a later env var must win on its own.
    assert current_version("conversation") == "2.0"


def test_registry_accepts_an_additional_schema_block_from_config(monkeypatch, tmp_path):
    """Adding a record type is a pure config edit (finding 3).

    The old SchemaRegistry hardcoded ``conversation`` / ``extraction`` fields
    with ``extra="forbid"``, so a third block was a startup ValidationError —
    contradicting the "evolve schemas via a config edit" design goal.
    """
    path = _write_config(
        tmp_path,
        """
        conversation:
          current: "1.0"
          supported: ["1.0"]
        extraction:
          current: "1.0"
          supported: ["1.0"]
        soap_note:
          current: "1.0"
          supported: ["1.0"]
        compatibility:
          on_unknown_version: "error"
        """,
    )
    _use_config(monkeypatch, path)

    assert current_version("soap_note") == "1.0"
    assert supported_versions("soap_note") == ("1.0",)


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


def test_check_version_warn_policy_logs_on_unknown(monkeypatch, tmp_path, caplog):
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

    with caplog.at_level(logging.WARNING, logger="src.schemas.versioning"):
        status = check_version("conversation", "0.1")
    assert status is CompatibilityStatus.UNKNOWN
    assert any("0.1" in r.getMessage() for r in caplog.records)


def test_check_version_strict_override_beats_config(caplog):
    # config policy is "error" here, but strict=False downgrades to a log line
    with caplog.at_level(logging.WARNING, logger="src.schemas.versioning"):
        check_version("conversation", "0.1", strict=False)
    assert any("0.1" in r.getMessage() for r in caplog.records)


def test_warn_policy_logs_one_record_per_call(monkeypatch, tmp_path, caplog):
    """Bulk-checking N records under "warn" must yield N notices, not 1 (finding 4).

    warnings.warn() de-duplicates by (message, module, lineno) under the
    default filter, so the old implementation emitted a single notice for a
    whole dataset and an operator tallying incompatible rows undercounted.
    """
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

    with caplog.at_level(logging.WARNING, logger="src.schemas.versioning"):
        for _ in range(5):
            check_version("conversation", "0.9")

    hits = [r for r in caplog.records if "0.9" in r.getMessage()]
    assert len(hits) == 5
