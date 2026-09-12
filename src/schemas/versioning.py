"""Config-driven schema versioning for persisted records.

Every top-level record this system stores — a patient ``ConversationSession``
(:mod:`src.schemas.conversation`) and a ``StructuredExtraction``
(:mod:`src.schemas.extraction`) — carries a ``schema_version`` string. The
value new records are stamped with, and the set of versions a consumer here
knows how to read, come from ``configs/schema.yaml``, read lazily on first use
and then memoised — **not** from a constant hardcoded next to each model
(nothing here reads the config at import time, so a malformed file cannot
break ``import src.schemas``). Bumping a schema is
then a config edit plus a migration note (``docs/schema-versioning.md``), and
older persisted records stay distinguishable from newer ones.

Config-file resolution, in order:

1. an explicit ``path`` passed to :func:`load_registry`;
2. ``$CLINICAL_AI_SCHEMA_CONFIG``;
3. ``configs/schema.yaml`` at the repo root (the default).

Per robustness rule 7 (repo ``CLAUDE.md``): a missing file at the *default*
location falls back to :data:`BUILTIN_DEFAULTS` so a fresh checkout still
works; a path supplied *explicitly* via (1) or (2) that does not exist is a
hard error, never a silent fall-through to defaults.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "schema.yaml"
ENV_VAR = "CLINICAL_AI_SCHEMA_CONFIG"

# Used only when no config file exists at the default path. This mirrors
# configs/schema.yaml; test_builtin_defaults_match_shipped_config asserts the
# two stay identical, so a drift fails CI rather than shipping two behaviours.
BUILTIN_DEFAULTS: dict = {
    "conversation": {"current": "1.0", "supported": ["1.0"]},
    "extraction": {"current": "1.0", "supported": ["1.0"]},
    "compatibility": {"on_unknown_version": "error"},
}


class IncompatibleSchemaVersionError(ValueError):
    """A record's ``schema_version`` is not one this codebase can read."""


class SchemaSpec(BaseModel):
    """Version info for one named schema (``conversation``, ``extraction``, ...)."""

    model_config = ConfigDict(extra="forbid")

    current: str = Field(..., min_length=1, description="Version new records are stamped with")
    supported: list[str] = Field(
        ..., min_length=1, description="Every version a consumer here can read"
    )

    @field_validator("supported")
    @classmethod
    def _supported_entries_non_empty(cls, value: list[str]) -> list[str]:
        if any(not entry for entry in value):
            raise ValueError("every entry in `supported` must be a non-empty version string")
        if len(set(value)) != len(value):
            raise ValueError("`supported` contains duplicate version strings")
        return value

    @model_validator(mode="after")
    def _current_is_supported(self) -> SchemaSpec:
        if self.current not in self.supported:
            raise ValueError(
                f"`current` version {self.current!r} is not listed in `supported` {self.supported}"
            )
        return self


class CompatibilityPolicy(BaseModel):
    """What to do with a record whose version is unknown to this codebase."""

    model_config = ConfigDict(extra="forbid")

    on_unknown_version: Literal["error", "warn"] = "error"


class SchemaRegistry(BaseModel):
    """The whole ``configs/schema.yaml`` document, validated.

    Every top-level key other than ``compatibility`` is a named schema block
    (``conversation``, ``extraction``, a future ``soap_note`` …) folded into
    :attr:`schemas`. Adding a persisted record type is therefore a pure config
    edit — no new field here and no source change, which is the whole point of
    keeping versions in a config file.
    """

    model_config = ConfigDict(extra="forbid")

    schemas: dict[str, SchemaSpec] = Field(..., min_length=1)
    compatibility: CompatibilityPolicy = Field(default_factory=CompatibilityPolicy)

    @model_validator(mode="before")
    @classmethod
    def _fold_named_blocks(cls, data: object) -> object:
        """Fold top-level schema blocks into ``schemas``.

        ``{conversation: {...}, extraction: {...}, compatibility: {...}}``
        becomes ``{schemas: {conversation: {...}, extraction: {...}},
        compatibility: {...}}``. An explicit ``schemas:`` mapping (or any
        non-dict, left for the field validators to reject) passes through
        untouched.
        """
        if not isinstance(data, dict) or "schemas" in data:
            return data
        folded: dict = {"schemas": {}}
        for key, value in data.items():
            if key == "compatibility":
                folded[key] = value
            else:
                folded["schemas"][key] = value
        return folded

    def spec(self, schema_name: str) -> SchemaSpec:
        """Return the :class:`SchemaSpec` for ``schema_name`` or raise ``KeyError``."""
        try:
            return self.schemas[schema_name]
        except KeyError:
            raise KeyError(
                f"unknown schema name {schema_name!r}; known: {sorted(self.schemas)}"
            ) from None


def _read_yaml_mapping(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"schema config at {path} is not a YAML mapping")
    return data


def _resolve_source(path: str | None) -> tuple[str | None, str | None]:
    """Resolve the config source to a concrete ``(path, label)`` before caching.

    The ``$CLINICAL_AI_SCHEMA_CONFIG`` lookup happens *here*, not inside the
    memoised function, so every input the result depends on is part of the
    cache key. If the env var is set (or changed) after the first call, the key
    changes and the new value is honoured — never silently ignored because an
    earlier ``path=None`` call cached the default (repo CLAUDE.md rule 7).
    """
    if path is not None:
        return path, "path argument"
    env = os.environ.get(ENV_VAR)
    if env is not None:
        return env, f"${ENV_VAR}"
    return None, None


@lru_cache(maxsize=None)
def _load_registry_cached(source: str | None, label: str | None) -> SchemaRegistry:
    if source is not None:
        config_path = Path(source)
        if not config_path.is_file():
            raise FileNotFoundError(
                f"schema config {config_path} (from {label}) does not exist"
            )
        return SchemaRegistry.model_validate(_read_yaml_mapping(config_path))

    if DEFAULT_CONFIG_PATH.is_file():
        return SchemaRegistry.model_validate(_read_yaml_mapping(DEFAULT_CONFIG_PATH))
    return SchemaRegistry.model_validate(BUILTIN_DEFAULTS)


def load_registry(path: str | None = None) -> SchemaRegistry:
    """Load and validate the schema registry, memoised per resolved source.

    Resolution order (see module docstring): explicit ``path`` →
    ``$CLINICAL_AI_SCHEMA_CONFIG`` → ``configs/schema.yaml`` → builtin
    defaults. The env var is read on every call, so setting it later takes
    effect; only edits to an already-resolved file need :func:`reload_registry`
    (tests, hot config edits).
    """
    return _load_registry_cached(*_resolve_source(path))


def reload_registry() -> None:
    """Drop the memoised registry so the next lookup re-reads the config file."""
    _load_registry_cached.cache_clear()


def current_version(schema_name: str) -> str:
    """The version string new ``schema_name`` records should be stamped with."""
    return load_registry().spec(schema_name).current


def supported_versions(schema_name: str) -> tuple[str, ...]:
    """Every version of ``schema_name`` a consumer in this codebase can read."""
    return tuple(load_registry().spec(schema_name).supported)


class CompatibilityStatus(str, Enum):
    """How a record's ``schema_version`` relates to the current registry."""

    CURRENT = "current"
    OLDER_SUPPORTED = "older_supported"
    UNKNOWN = "unknown"


def classify_version(schema_name: str, version: str) -> CompatibilityStatus:
    """Bucket ``version`` against the registry without raising."""
    spec = load_registry().spec(schema_name)
    if version == spec.current:
        return CompatibilityStatus.CURRENT
    if version in spec.supported:
        return CompatibilityStatus.OLDER_SUPPORTED
    return CompatibilityStatus.UNKNOWN


def check_version(
    schema_name: str, version: str, *, strict: bool | None = None
) -> CompatibilityStatus:
    """Validate a record's ``schema_version`` against the registry.

    Returns the :class:`CompatibilityStatus`. ``CURRENT`` and
    ``OLDER_SUPPORTED`` pass through. For ``UNKNOWN`` the behaviour follows
    ``compatibility.on_unknown_version`` in the config (``"error"`` raises
    :class:`IncompatibleSchemaVersionError`, ``"warn"`` logs a warning on
    :data:`logger` and returns), unless ``strict`` overrides it:
    ``strict=True`` always raises, ``strict=False`` always logs.

    The "warn" path uses the :mod:`logging` module, not :func:`warnings.warn`:
    the latter is de-duplicated by (message, module, lineno) under the default
    filter, so bulk-checking many records with the same unknown version would
    emit only one notice and an operator tallying incompatible rows would
    undercount. One log record per call keeps the count honest.
    """
    status = classify_version(schema_name, version)
    if status is not CompatibilityStatus.UNKNOWN:
        return status

    policy = load_registry().compatibility.on_unknown_version
    should_raise = (policy == "error") if strict is None else strict
    message = (
        f"{schema_name} record has schema_version {version!r}, which is not in "
        f"supported versions {list(supported_versions(schema_name))}; "
        f"see docs/schema-versioning.md for how to migrate it"
    )
    if should_raise:
        raise IncompatibleSchemaVersionError(message)
    logger.warning(message)
    return status


class VersionedRecord(BaseModel):
    """Base for a persisted top-level record carrying a config-driven version.

    A subclass sets :attr:`SCHEMA_NAME` to a key in ``configs/schema.yaml``.
    Creating a record without an explicit ``schema_version`` stamps it with
    that schema's ``current`` version from config; supplying one (e.g. when
    loading a stored record) runs it through :func:`check_version`, so an
    unknown shape fails loudly at parse time instead of flowing downstream.
    """

    SCHEMA_NAME: ClassVar[str]

    schema_version: str = Field(
        default="",
        description="Schema version the record was written with (from configs/schema.yaml)",
    )

    @model_validator(mode="after")
    def _stamp_or_check_version(self) -> VersionedRecord:
        schema_name = getattr(type(self), "SCHEMA_NAME", None)
        if not schema_name:
            raise TypeError(
                f"{type(self).__name__} must set SCHEMA_NAME to a key in configs/schema.yaml"
            )
        if not self.schema_version:
            self.schema_version = current_version(schema_name)
        else:
            check_version(schema_name, self.schema_version)
        return self
