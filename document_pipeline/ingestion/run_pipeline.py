"""Run the approved-source collection and manifest build in one command."""
from __future__ import annotations

import argparse
from pathlib import Path

try:  # Supports both `python -m` and direct script execution.
    from .build_manifest import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_OVERLAP_TOKENS,
        DEFAULT_TARGET_TOKENS,
        DEFAULT_TOKENIZER_NAME,
        MANIFEST_PATH,
        PROCESSED_ROOT,
        build_manifest,
    )
    from .fetch import RAW_ROOT, REGISTRY_PATH, fetch_sources
except ImportError:  # pragma: no cover - direct invocation path
    from build_manifest import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_OVERLAP_TOKENS,
        DEFAULT_TARGET_TOKENS,
        DEFAULT_TOKENIZER_NAME,
        MANIFEST_PATH,
        PROCESSED_ROOT,
        build_manifest,
    )
    from fetch import RAW_ROOT, REGISTRY_PATH, fetch_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect approved documents and build the PiCare manifest.")
    parser.add_argument("--commit", help="Optional 40-character Raspberry Pi documentation commit SHA")
    parser.add_argument("--tokenizer-name", default=DEFAULT_TOKENIZER_NAME)
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    parser.add_argument("--source-registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=PROCESSED_ROOT)
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()

    ledger = fetch_sources(
        commit=args.commit,
        raw_root=args.raw_root,
        registry_path=args.source_registry,
    )
    manifest = build_manifest(
        raw_root=args.raw_root,
        processed_root=args.processed_root,
        output_path=args.manifest_path,
        registry_path=args.source_registry,
        tokenizer_name=args.tokenizer_name,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    print(f"commit: {ledger['commit']}")
    print(f"documents: {len(ledger['documents'])}")
    print(f"chunks: {len(manifest['chunks'])}")
    print(f"manifest: {args.manifest_path}")


if __name__ == "__main__":
    main()
