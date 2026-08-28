"""Run the approved-source collection and manifest build in one command."""
from __future__ import annotations

import argparse

try:  # Supports both `python -m` and direct script execution.
    from .build_manifest import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_OVERLAP_TOKENS,
        DEFAULT_TARGET_TOKENS,
        DEFAULT_TOKENIZER_NAME,
        build_manifest,
    )
    from .fetch import fetch_sources
except ImportError:  # pragma: no cover - direct invocation path
    from build_manifest import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_OVERLAP_TOKENS,
        DEFAULT_TARGET_TOKENS,
        DEFAULT_TOKENIZER_NAME,
        build_manifest,
    )
    from fetch import fetch_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect approved documents and build the PiCare manifest.")
    parser.add_argument("--commit", help="Optional 40-character Raspberry Pi documentation commit SHA")
    parser.add_argument("--tokenizer-name", default=DEFAULT_TOKENIZER_NAME)
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    args = parser.parse_args()

    ledger = fetch_sources(commit=args.commit)
    manifest = build_manifest(
        tokenizer_name=args.tokenizer_name,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    print(f"commit: {ledger['commit']}")
    print(f"documents: {len(ledger['documents'])}")
    print(f"chunks: {len(manifest['chunks'])}")


if __name__ == "__main__":
    main()
