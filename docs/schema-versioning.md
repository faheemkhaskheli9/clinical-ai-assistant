# Schema versioning & compatibility

Persisted records in this project carry an explicit `schema_version` so stored
data and prompts can evolve without silently breaking older sessions. This
note describes where the version comes from and how a consumer should treat a
record whose version isn't the current one.

## Where the version lives

`configs/schema.yaml` is the single source of truth. It is read **once at
startup** by `src/schemas/versioning.py` — there is no version constant
hardcoded next to a model.

```yaml
conversation:
  current: "1.0"        # value new records are stamped with
  supported: ["1.0"]    # every version a consumer here can read
extraction:
  current: "1.0"
  supported: ["1.0"]
compatibility:
  on_unknown_version: "error"   # or "warn"
```

Config-file resolution order:

1. explicit `path=` argument to `load_registry()`
2. `$CLINICAL_AI_SCHEMA_CONFIG`
3. `configs/schema.yaml` at the repo root (default)

A missing file at the **default** location falls back to
`versioning.BUILTIN_DEFAULTS` (a fresh checkout still runs). A path given
**explicitly** via (1) or (2) that doesn't exist is a hard error — you asked
for specific settings, so a silent fall-through to defaults would be a lie.

## How records get stamped

`ConversationSession` and `StructuredExtraction` both subclass
`VersionedRecord`:

- created **without** `schema_version` → stamped with `current` from config;
- created **with** `schema_version` (e.g. loading a stored row) → run through
  `check_version()` before the object is returned.

```python
from src.schemas import ConversationSession, current_version

current_version("conversation")            # -> "1.0"
ConversationSession(patient_id="p-1").schema_version   # -> "1.0"
```

## Consuming a record whose version isn't current

`check_version(schema_name, version)` returns a `CompatibilityStatus`:

| Status | Meaning | What the consumer should do |
|---|---|---|
| `CURRENT` | `version == current` | Use the record directly. |
| `OLDER_SUPPORTED` | in `supported`, not `current` | Read it. Fields added since that version are absent — rely on model defaults; do **not** back-fill guesses. Persist a re-stamped copy only through an explicit migration, never as a silent side effect of a read. |
| `UNKNOWN` | not in `supported` | Follow `compatibility.on_unknown_version`: `error` raises `IncompatibleSchemaVersionError` (default — a wrong result from misreading an unknown shape is worse than a loud failure); `warn` logs and proceeds best-effort. Override per call with `check_version(..., strict=True/False)`. |

Keep the original stored record as the record of truth. A distilled or
re-stamped copy is derived data, not a replacement for the source row.

## Changing a schema

1. **Additive / backward-compatible** (new *optional* field, wider enum):
   keep the version. Old records still validate under the new model's
   defaults. No migration needed.
2. **Breaking** (field removed / renamed / retyped, semantics changed):
   - add the new version string to `current`;
   - keep the previous version in `supported` until a migration has
     back-filled or retired every stored record;
   - add a dated entry to the changelog below describing the change and the
     migration step;
   - once no stored record uses the old version, drop it from `supported`.

## Changelog

| Date | Schema | Version | Change | Migration |
|---|---|---|---|---|
| 2026-08-27 | conversation, extraction | 1.0 | Initial versioned schema. | — |
