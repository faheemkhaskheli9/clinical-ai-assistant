"""CLI: fetch public medical reference data online and store it locally.

Usage:
    python scripts/ingest.py
    python scripts/ingest.py --sources medlineplus,openfda
    python scripts/ingest.py --config configs/ingest.yaml

Raw responses are cached under data/raw/, normalized documents are written
as JSONL under data/processed/<source>.jsonl (both gitignored — local cache,
not tracked data). Re-running is cheap: MedlinePlus/MedQuAD raw responses
are cached to disk and skipped on a second run; openFDA is re-queried since
its result set changes over time. Processed JSONL is always overwritten in
full so a run never leaves stale/duplicate records behind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # allow running as `python scripts/ingest.py`

from src.rag.fetchers import medlineplus, medquad, openfda  # noqa: E402
from src.rag.storage import write_documents  # noqa: E402

FETCHERS = {
    "medlineplus": medlineplus.fetch,
    "openfda": openfda.fetch,
    "medquad": medquad.fetch,
}


DEFAULT_CONFIG = REPO_ROOT / "configs" / "ingest.yaml"


def load_config(path: Path, *, required: bool) -> dict:
    """Load a per-source YAML config.

    ``required`` is True when the user passed ``--config`` explicitly: a
    missing/typo'd path is then a hard error rather than a silent fall-through
    to built-in defaults (which would run with the wrong limits and no
    warning). The built-in default path is allowed to be absent.
    """
    if not path.exists():
        if required:
            raise SystemExit(f"--config: no such file: {path}")
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def run(sources: list[str], config: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        fetch = FETCHERS.get(source)
        if fetch is None:
            print(f"[skip] unknown source: {source!r} (known: {', '.join(FETCHERS)})", file=sys.stderr)
            continue

        kwargs = {k: v for k, v in (config.get(source) or {}).items() if v is not None}
        print(f"[{source}] fetching ({kwargs or 'defaults'}) ...")
        documents = fetch(**kwargs)
        count = write_documents(source, documents)
        counts[source] = count
        print(f"[{source}] wrote {count} documents -> data/processed/{source}.jsonl")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--sources",
        default="medlineplus,openfda,medquad",
        help="Comma-separated source names to ingest (default: all three)",
    )
    parser.add_argument(
        "--config",
        default=None,
        type=Path,
        help=f"YAML file of per-source keyword arguments (default: {DEFAULT_CONFIG})",
    )
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    config = load_config(
        args.config if args.config is not None else DEFAULT_CONFIG,
        required=args.config is not None,
    )
    counts = run(sources, config)

    total = sum(counts.values())
    print(f"\nDone. {total} documents written across {len(counts)} source(s).")


if __name__ == "__main__":
    main()
