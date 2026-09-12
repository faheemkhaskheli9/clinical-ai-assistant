"""Regenerate the committed JSON Schema / tool-definition exports.

Run after changing anything under ``src/schemas/`` so the cross-language
references under ``docs/schemas/`` stay in sync with the Pydantic models:

    python scripts/export_schema.py

``tests/schemas/test_schema_exports.py`` fails if a committed file drifts from
what this script would produce, so drift is caught in CI rather than shipped.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.schemas.conversation import ConversationSession
from src.schemas.extraction import StructuredExtraction, extraction_function_tool

DOCS_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "docs" / "schemas"

# filename -> JSON-serialisable payload. Order/keys are preserved verbatim so
# the committed file and this in-memory value compare byte-for-byte.
EXPORTS: dict[str, object] = {
    "conversation.schema.json": ConversationSession.model_json_schema(),
    "extraction.schema.json": StructuredExtraction.model_json_schema(),
    "extraction.function_tool.json": extraction_function_tool(),
}


def render(payload: object) -> str:
    """The exact text a committed export file should contain for ``payload``."""
    return json.dumps(payload, indent=2) + "\n"


def main() -> None:
    DOCS_SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload in EXPORTS.items():
        path = DOCS_SCHEMAS_DIR / filename
        path.write_text(render(payload), encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
