"""Link reviewed guide media to canonical document-manifest chunks.

Media is display-only evidence.  The document chunk remains the factual source,
and an item is never linked when its document URL and section cannot both be
matched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _normalise_document_url(value: str) -> str:
    """Compare official page URLs without anchors or a trailing slash."""
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def _section_matches(chunk_section: str, media_section: str) -> bool:
    return media_section.casefold() in chunk_section.casefold()


def _guide_items(payload: dict[str, Any], *, source: Path) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError(f"media manifest items must be an array: {source}")
    guides: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"media manifest item must be an object: {source}")
        if item.get("category") == "guide":
            guides.append(item)
    return guides


def _validate_image(item: dict[str, Any], *, repository_root: Path) -> None:
    relative_path = item.get("relative_path")
    expected_checksum = item.get("checksum")
    if not isinstance(relative_path, str) or not isinstance(expected_checksum, str):
        raise ValueError(f"image path/checksum missing: {item.get('media_id')}")
    image_path = repository_root / relative_path
    if not image_path.is_file():
        raise ValueError(f"image file missing: {image_path}")
    if _sha256_file(image_path) != expected_checksum:
        raise ValueError(f"image checksum mismatch: {item.get('media_id')}")


def _validate_video(item: dict[str, Any]) -> None:
    if item.get("official_verified") is not True or item.get("embed_allowed") is not True:
        raise ValueError(f"video is not approved for official embedding: {item.get('media_id')}")
    embed_url = item.get("embed_url")
    if not isinstance(embed_url, str) or not embed_url.startswith("https://www.youtube.com/embed/"):
        raise ValueError(f"invalid YouTube embed URL: {item.get('media_id')}")


def build_media_chunk_map(
    *,
    document_manifest_path: Path,
    image_manifest_path: Path,
    video_manifest_path: Path,
    output_path: Path,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic media-to-chunk map from reviewed manifests."""
    document_manifest_path = document_manifest_path.resolve()
    image_manifest_path = image_manifest_path.resolve()
    video_manifest_path = video_manifest_path.resolve()
    output_path = output_path.resolve()
    repository_root = (repository_root or Path.cwd()).resolve()

    document_manifest = _read_json(document_manifest_path)
    chunks = document_manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("document manifest must contain at least one chunk")

    image_payload = _read_json(image_manifest_path)
    video_payload = _read_json(video_manifest_path)
    media_items = _guide_items(image_payload, source=image_manifest_path) + _guide_items(
        video_payload, source=video_manifest_path
    )

    seen_ids: set[str] = set()
    links: list[dict[str, Any]] = []
    unmatched: list[dict[str, str]] = []

    for item in media_items:
        media_id = item.get("media_id")
        media_type = item.get("media_type")
        source_url = item.get("source_document_url")
        source_section = item.get("source_section")
        if not all(isinstance(value, str) and value for value in (media_id, media_type, source_url, source_section)):
            raise ValueError("guide media requires media_id, media_type, source_document_url, and source_section")
        if media_id in seen_ids:
            raise ValueError(f"duplicate media ID: {media_id}")
        seen_ids.add(media_id)

        if media_type == "image":
            _validate_image(item, repository_root=repository_root)
        elif media_type == "video":
            _validate_video(item)
        else:
            raise ValueError(f"unsupported guide media type: {media_type}")

        normalised_url = _normalise_document_url(source_url)
        allowed_document_ids = item.get("document_ids")
        if allowed_document_ids is not None and not isinstance(allowed_document_ids, list):
            raise ValueError(f"document_ids must be an array: {media_id}")

        url_candidates = [
            chunk
            for chunk in chunks
            if isinstance(chunk, dict)
            and isinstance(chunk.get("source_url"), str)
            and _normalise_document_url(chunk["source_url"]) == normalised_url
            and (not allowed_document_ids or chunk.get("document_id") in allowed_document_ids)
        ]
        section_candidates = [
            chunk
            for chunk in url_candidates
            if isinstance(chunk.get("section"), str) and _section_matches(chunk["section"], source_section)
        ]

        if not url_candidates:
            unmatched.append(
                {
                    "media_id": media_id,
                    "reason": "document_url_not_in_corpus",
                    "source_document_url": source_url,
                    "source_section": source_section,
                }
            )
            continue
        if not section_candidates:
            unmatched.append(
                {
                    "media_id": media_id,
                    "reason": "section_not_in_collected_document",
                    "source_document_url": source_url,
                    "source_section": source_section,
                }
            )
            continue

        chunk_ids = sorted({str(chunk["chunk_id"]) for chunk in section_candidates})
        document_ids = sorted({str(chunk["document_id"]) for chunk in section_candidates})
        links.append(
            {
                "media_id": media_id,
                "media_type": media_type,
                "document_ids": document_ids,
                "chunk_ids": chunk_ids,
            }
        )

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "document_manifest": document_manifest_path.name,
        "document_manifest_checksum": _sha256_file(document_manifest_path),
        "image_manifest_checksum": _sha256_file(image_manifest_path),
        "video_manifest_checksum": _sha256_file(video_manifest_path),
        "summary": {
            "guide_media_total": len(media_items),
            "linked_media": len(links),
            "unmatched_media": len(unmatched),
        },
        "links": links,
        "unmatched": unmatched,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Link reviewed Raspberry Pi media to document chunks.")
    parser.add_argument("--document-manifest", type=Path, required=True)
    parser.add_argument("--image-manifest", type=Path, default=Path("assets/media/manifest.json"))
    parser.add_argument("--video-manifest", type=Path, default=Path("assets/media/video_manifest.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    payload = build_media_chunk_map(
        document_manifest_path=args.document_manifest,
        image_manifest_path=args.image_manifest,
        video_manifest_path=args.video_manifest,
        output_path=args.output,
        repository_root=args.repository_root,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
