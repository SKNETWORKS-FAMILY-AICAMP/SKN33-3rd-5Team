"""Run the approved-source collection and manifest build in one command."""
from __future__ import annotations

import argparse

try:  # Supports both `python -m` and direct script execution.
    from .build_manifest import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, build_manifest
    from .fetch import fetch_sources
except ImportError:  # pragma: no cover - direct invocation path
    from build_manifest import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, build_manifest
    from fetch import fetch_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect approved documents and build the PiCare manifest.")
    parser.add_argument("--commit", help="Optional 40-character Raspberry Pi documentation commit SHA")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    args = parser.parse_args()

    ledger = fetch_sources(commit=args.commit)
    manifest = build_manifest(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print(f"commit: {ledger['commit']}")
    print(f"documents: {len(ledger['documents'])}")
    print(f"chunks: {len(manifest['chunks'])}")


if __name__ == "__main__":
    main()
