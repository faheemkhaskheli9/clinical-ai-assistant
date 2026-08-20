"""Regenerate the committed JSON Schema export for the conversation models.

Run after changing ``src/schemas/conversation.py`` so the cross-language
reference under ``docs/schemas/`` stays in sync with the Pydantic models:

    python scripts/export_schema.py
"""

from __future__ import annotations

import json
from pathlib import Path

from src.schemas.conversation import ConversationSession

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "schemas" / "conversation.schema.json"


def main() -> None:
    schema = ConversationSession.model_json_schema()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
