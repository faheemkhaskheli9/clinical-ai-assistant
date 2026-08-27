import importlib.util
from pathlib import Path

import pytest

_INGEST_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ingest.py"
_spec = importlib.util.spec_from_file_location("ingest_cli", _INGEST_PATH)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


def test_load_config_returns_empty_when_default_path_absent(tmp_path):
    missing = tmp_path / "ingest.yaml"
    assert ingest.load_config(missing, required=False) == {}


def test_load_config_raises_when_explicit_path_absent(tmp_path):
    missing = tmp_path / "typo.yaml"
    with pytest.raises(SystemExit):
        ingest.load_config(missing, required=True)


def test_load_config_parses_existing_file(tmp_path):
    cfg = tmp_path / "ingest.yaml"
    cfg.write_text("openfda:\n  limit: 5\n", encoding="utf-8")
    assert ingest.load_config(cfg, required=True) == {"openfda": {"limit": 5}}
