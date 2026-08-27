"""Config-driven schema versioning for persisted records.

Every top-level record this system stores — a patient ``ConversationSession``
(:mod:`src.schemas.conversation`) and a ``StructuredExtraction``
(:mod:`src.schemas.extraction`) — carries a ``schema_version`` string. The
value new records are stamped with, and the set of versions a consumer here
knows how to read, come from ``configs/schema.yaml`` read once at startup —
**not** from a constant hardcoded next to each model. Bumping a schema is
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

import os
import warnings
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "schema.yaml"
ENV_VAR = "CLINICAL_AI_SCHEMA_CONFIG"

# Used only when no config file exists at the default path. Keep in sync with
# configs/schema.yaml so behaviour doesn't shift when the file is present.
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
    """The whole ``configs/schema.yaml`` document, validated."""

    model_config = ConfigDict(extra="forbid")

    conversation: SchemaSpec
    extraction: SchemaSpec
    compatibility: CompatibilityPolicy = Field(default_factory=CompatibilityPolicy)

    def spec(self, schema_name: str) -> SchemaSpec:
        """Return the :class:`SchemaSpec` for ``schema_name`` or raise ``KeyError``."""
        candidate = getattr(self, schema_name, None)
        if not isinstance(candidate, SchemaSpec):
            known = [n for n, f in type(self).model_fields.items() if f.annotation is SchemaSpec]
            raise KeyError(f"unknown schema name {schema_name!r}; known: {known}")
        return candidate


def _read_yaml_mapping(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"schema config at {path} is not a YAML mapping")
    return data


@lru_cache(maxsize=None)
def load_registry(path: str | None = None) -> SchemaRegistry:
    """Load and validate the schema registry, memoised per distinct ``path``.

    See the module docstring for resolution order and the missing-file rules.
    Call :func:`reload_registry` to force a re-read (tests, hot config edits).
    """
    explicit = path if path is not None else os.environ.get(ENV_VAR)
    if explicit is not None:
        source = "path argument" if path is not None else f"${ENV_VAR}"
        config_path = Path(explicit)
        if not config_path.is_file():
            raise FileNotFoundError(
                f"schema config {config_path} (from {source}) does not exist"
            )
        return SchemaRegistry.model_validate(_read_yaml_mapping(config_path))

    if DEFAULT_CONFIG_PATH.is_file():
        return SchemaRegistry.model_validate(_read_yaml_mapping(DEFAULT_CONFIG_PATH))
    return SchemaRegistry.model_validate(BUILTIN_DEFAULTS)


def reload_registry() -> None:
    """Drop the memoised registry so the next lookup re-reads the config file."""
    load_registry.cache_clear()


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
    :class:`IncompatibleSchemaVersionError`, ``"warn"`` emits a warning and
    returns), unless ``strict`` overrides it: ``strict=True`` always raises,
    ``strict=False`` always warns.
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
    warnings.warn(message, stacklevel=2)
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
