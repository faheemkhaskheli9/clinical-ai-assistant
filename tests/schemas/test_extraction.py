"""Tests for the structured-extraction record (src/schemas/extraction.py)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.schemas.extraction import StructuredExtraction, Vitals
from src.schemas.versioning import reload_registry


@pytest.fixture(autouse=True)
def _clean_registry_cache():
    reload_registry()
    yield
    reload_registry()


def _payload() -> dict:
    return {"session_id": str(uuid4()), "patient_id": "patient-pseudo-9001"}


def test_minimal_extraction_is_stamped_from_config():
    record = StructuredExtraction.model_validate(_payload())

    assert record.schema_version == "1.0"
    assert record.symptoms == []
    assert record.vitals == Vitals()
    assert record.extraction_id is not None


def test_explicit_supported_version_is_accepted():
    record = StructuredExtraction(**_payload(), schema_version="1.0")
    assert record.schema_version == "1.0"


def test_unknown_version_is_rejected():
    with pytest.raises(ValidationError):
        StructuredExtraction(**_payload(), schema_version="0.0")


def test_patient_id_rejects_email_shaped_values():
    payload = _payload()
    payload["patient_id"] = "someone@example.com"
    with pytest.raises(ValidationError):
        StructuredExtraction.model_validate(payload)


def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        StructuredExtraction.model_validate({**_payload(), "unexpected": "x"})


def test_oxygen_saturation_is_bounded():
    with pytest.raises(ValidationError):
        StructuredExtraction(**_payload(), vitals={"oxygen_saturation": 150})
