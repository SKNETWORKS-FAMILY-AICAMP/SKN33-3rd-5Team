"""Run the approved-source collection and manifest build in one command."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Keep the documented direct-script invocation working as well as ``python -m``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.media.linker import build_media_chunk_map
from src.rag import RagSettings, RagSettingsError, index_from_settings

try:  # Supports both `python -m` and direct script execution.
    from .build_media_manifest import MEDIA_MANIFEST_PATH, build_media_manifest
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
    from build_media_manifest import MEDIA_MANIFEST_PATH, build_media_manifest
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


V3_REGISTRY_PATH = REGISTRY_PATH.with_name("source_registry_v3.csv")
V3_RAW_ROOT = RAW_ROOT.with_name("raw_v3")
V3_PROCESSED_ROOT = PROCESSED_ROOT.with_name("processed_v3")
V3_MANIFEST_PATH = MANIFEST_PATH.with_name("manifest_v3.json")
V3_MEDIA_MANIFEST_PATH = MEDIA_MANIFEST_PATH.with_name("media_manifest_v3.json")
V3_MEDIA_CHUNK_MAP_PATH = MANIFEST_PATH.with_name("media_chunk_map_v3.json")
DEFAULT_IMAGE_MANIFEST_PATH = Path("assets/media/manifest.json")
DEFAULT_VIDEO_MANIFEST_PATH = Path("assets/media/video_manifest.json")
DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _reset_index_for_manifest(
    *,
    manifest_path: Path,
    media_manifest_path: Path,
    media_chunk_map_path: Path,
    repository_root: Path,
) -> int:
    """방금 생성한 manifest를 기존 QA와 같은 Chroma 설정으로 전체 재색인한다."""
    settings = RagSettings.from_env(repository_root)
    expected_paths = {
        "DOCUMENT_MANIFEST": (settings.manifest_path, manifest_path),
        "MEDIA_MANIFEST": (settings.media_manifest_path, media_manifest_path),
        "MEDIA_CHUNK_MAP": (settings.media_chunk_map_path, media_chunk_map_path),
    }
    for setting_name, (configured_path, generated_path) in expected_paths.items():
        if configured_path is None or configured_path.resolve() != generated_path.resolve():
            raise ValueError(
                f"{setting_name} must match the run_pipeline output: {generated_path}"
            )
    return index_from_settings(settings, manifest_path=manifest_path, reset=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect approved documents and build the PiCare manifest.")
    parser.add_argument("--commit", help="Optional 40-character Raspberry Pi documentation commit SHA")
    parser.add_argument("--tokenizer-name", default=DEFAULT_TOKENIZER_NAME)
    parser.add_argument("--tokenizer-revision")
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    parser.add_argument("--source-registry", type=Path, default=V3_REGISTRY_PATH)
    parser.add_argument("--raw-root", type=Path, default=V3_RAW_ROOT)
    parser.add_argument("--processed-root", type=Path, default=V3_PROCESSED_ROOT)
    parser.add_argument("--manifest-path", type=Path, default=V3_MANIFEST_PATH)
    parser.add_argument("--media-manifest-path", type=Path, default=V3_MEDIA_MANIFEST_PATH)
    parser.add_argument("--media-chunk-map-path", type=Path, default=V3_MEDIA_CHUNK_MAP_PATH)
    parser.add_argument("--image-manifest-path", type=Path, default=DEFAULT_IMAGE_MANIFEST_PATH)
    parser.add_argument("--video-manifest-path", type=Path, default=DEFAULT_VIDEO_MANIFEST_PATH)
    parser.add_argument("--repository-root", type=Path, default=DEFAULT_REPOSITORY_ROOT)
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
        tokenizer_revision=args.tokenizer_revision,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    media_manifest = build_media_manifest(
        document_manifest_path=args.manifest_path,
        raw_root=args.raw_root,
        registry_path=args.source_registry,
        output_path=args.media_manifest_path,
    )
    media_chunk_map = build_media_chunk_map(
        document_manifest_path=args.manifest_path,
        image_manifest_path=args.image_manifest_path,
        video_manifest_path=args.video_manifest_path,
        output_path=args.media_chunk_map_path,
        repository_root=args.repository_root,
    )
    try:
        indexed_chunk_count = _reset_index_for_manifest(
            manifest_path=args.manifest_path,
            media_manifest_path=args.media_manifest_path,
            media_chunk_map_path=args.media_chunk_map_path,
            repository_root=args.repository_root,
        )
    except RagSettingsError as exc:
        raise RuntimeError(f"RAG settings error: {exc}") from exc
    print(f"commit: {ledger['commit']}")
    print(f"documents: {len(ledger['documents'])}")
    print(f"chunks: {len(manifest['chunks'])}")
    print(f"manifest: {args.manifest_path}")
    print(f"media: {media_manifest['statistics']['media_items']}")
    print(f"media manifest: {args.media_manifest_path}")
    print(f"media links: {media_chunk_map['summary']['linked_media']}")
    print(f"unmatched media: {media_chunk_map['summary']['unmatched_media']}")
    print(f"media chunk map: {args.media_chunk_map_path}")
    print(f"indexed chunks: {indexed_chunk_count}")


if __name__ == "__main__":
    main()
