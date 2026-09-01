"""Build a citation-linked media manifest without creating media chunks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin, urlparse

try:  # Supports both `python -m` and direct script execution.
    from .fetch import PIPELINE_ROOT, RAW_ROOT, REGISTRY_PATH, REPOSITORY_ROOT, SourceRecord, included_sources
    from .parse_asciidoc import ParsedBlock, ParsedSection, parse_asciidoc
except ImportError:  # pragma: no cover - direct invocation path
    from fetch import PIPELINE_ROOT, RAW_ROOT, REGISTRY_PATH, REPOSITORY_ROOT, SourceRecord, included_sources
    from parse_asciidoc import ParsedBlock, ParsedSection, parse_asciidoc


DOCUMENT_MANIFEST_PATH = PIPELINE_ROOT / "data" / "manifest.json"
MEDIA_MANIFEST_PATH = PIPELINE_ROOT / "data" / "media_manifest.json"
MEDIA_MANIFEST_VERSION = "1.0.0"
MEDIA_LINKER_VERSION = "media-linker-1.0.0"
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
ALLOWED_IMAGE_HOSTS = {
    "raw.githubusercontent.com",
    "www.raspberrypi.com",
    "raspberrypi.com",
    "assets.raspberrypi.com",
}


def sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _project_reference(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("manifest inputs and outputs must be inside the project repository") from exc


def _safe_raw_path(raw_root: Path, relative_path: str) -> Path:
    candidate = (raw_root / relative_path).resolve()
    try:
        candidate.relative_to(raw_root.resolve())
    except ValueError as exc:
        raise ValueError(f"collection ledger contains an unsafe path: {relative_path}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"collected source is missing: {candidate}")
    return candidate


def _walk_media(block: ParsedBlock) -> Iterator[ParsedBlock]:
    if block.kind in {"image", "video"}:
        yield block
    for child in block.blocks:
        yield from _walk_media(child)


def media_blocks(section: ParsedSection) -> Iterator[ParsedBlock]:
    for block in section.blocks:
        yield from _walk_media(block)


def resolve_image_url(collection_url: str, target: str, *, source_commit: str) -> str:
    """Resolve an image only when it remains on an approved official host."""

    if not target or "{" in target or "}" in target:
        raise ValueError(f"unresolved image target: {target!r}")
    resolved = urljoin(collection_url, target)
    parsed = urlparse(resolved)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_IMAGE_HOSTS:
        raise ValueError(f"image URL is outside the approved official hosts: {resolved}")
    if parsed.hostname == "raw.githubusercontent.com":
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 4 or path_parts[:2] != ["raspberrypi", "documentation"]:
            raise ValueError(f"image URL is outside the official documentation repository: {resolved}")
        if path_parts[2] != source_commit:
            raise ValueError(f"image URL is not pinned to collection commit {source_commit}: {resolved}")
    return resolved


def resolve_video_url(target: str, platform: str | None) -> str:
    """Resolve explicitly declared video providers; never infer from free text."""

    if platform != "youtube" or not YOUTUBE_ID.fullmatch(target):
        raise ValueError(f"unsupported or malformed video macro: platform={platform!r}, target={target!r}")
    return f"https://www.youtube.com/watch?v={target}"


def _media_id(media_type: str, url: str) -> str:
    digest = hashlib.sha256(f"{media_type}\0{url}".encode("utf-8")).hexdigest()[:20]
    return f"media-{digest}"


def _load_inputs(
    *,
    document_manifest_path: Path,
    raw_root: Path,
    registry_path: Path,
) -> tuple[dict[str, object], dict[str, object], list[SourceRecord]]:
    manifest_bytes = document_manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != "1.1.0" or not isinstance(manifest.get("chunks"), list):
        raise ValueError("unsupported or malformed document manifest")

    ledger_path = raw_root / "collection.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != "1.0.0" or not isinstance(ledger.get("documents"), list):
        raise ValueError("unsupported or malformed collection ledger")

    registry_checksum = sha256_bytes(registry_path.read_bytes())
    manifest_registry_checksum = manifest.get("processing", {}).get("source_registry_checksum")
    if registry_checksum != manifest_registry_checksum:
        raise ValueError("document manifest was not generated from the selected source registry")
    expected_registry_ref = _project_reference(registry_path)
    if manifest.get("source_registry") != expected_registry_ref or ledger.get("source_registry") != expected_registry_ref:
        raise ValueError("document manifest, collection ledger and source registry do not match")
    return manifest, ledger, included_sources(registry_path)


def build_media_manifest(
    *,
    document_manifest_path: Path = DOCUMENT_MANIFEST_PATH,
    raw_root: Path = RAW_ROOT,
    registry_path: Path = REGISTRY_PATH,
    output_path: Path = MEDIA_MANIFEST_PATH,
) -> dict[str, object]:
    """Collect official media URLs and link them to approved chunks by document and section."""

    document_manifest_path = document_manifest_path.resolve()
    raw_root = raw_root.resolve()
    registry_path = registry_path.resolve()
    output_path = output_path.resolve()
    manifest, ledger, sources = _load_inputs(
        document_manifest_path=document_manifest_path,
        raw_root=raw_root,
        registry_path=registry_path,
    )

    source_by_id = {source.source_id: source for source in sources}
    ledger_by_id = {
        item["source_id"]: item
        for item in ledger["documents"]
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    if set(source_by_id) != set(ledger_by_id):
        raise ValueError("included source registry and collection ledger IDs do not match")

    chunks = manifest["chunks"]
    chunk_ids: set[str] = set()
    chunks_by_section: dict[tuple[str, str], list[str]] = defaultdict(list)
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("document manifest contains a malformed chunk")
        chunk_id = chunk.get("chunk_id")
        document_id = chunk.get("document_id")
        section = chunk.get("section")
        if not all(isinstance(value, str) and value for value in (chunk_id, document_id, section)):
            raise ValueError("document manifest contains a chunk without stable IDs or section")
        if chunk_id in chunk_ids:
            raise ValueError(f"duplicate chunk_id in document manifest: {chunk_id}")
        chunk_ids.add(chunk_id)
        chunks_by_section[(document_id, section)].append(chunk_id)

    source_commit = ledger.get("commit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("collection ledger has an invalid source commit")

    items_by_id: dict[str, dict[str, object]] = {}
    links_by_chunk: dict[str, list[str]] = defaultdict(list)
    occurrence_keys: set[tuple[str, str, str]] = set()
    media_occurrence_count = 0

    for source_id, source in source_by_id.items():
        ledger_item = ledger_by_id[source_id]
        relative_path = ledger_item.get("path")
        collection_url = ledger_item.get("collection_url")
        document_checksum = ledger_item.get("document_checksum")
        if not all(isinstance(value, str) and value for value in (relative_path, collection_url, document_checksum)):
            raise ValueError(f"{source_id}: malformed collection ledger entry")
        raw_path = _safe_raw_path(raw_root, relative_path)
        raw_bytes = raw_path.read_bytes()
        if sha256_bytes(raw_bytes) != document_checksum:
            raise ValueError(f"{source_id}: collected source checksum mismatch")
        sections = parse_asciidoc(raw_bytes.decode("utf-8"), fallback_title=source.title)

        for section in sections:
            section_name = " > ".join(section.heading_path)
            linked_chunk_ids = chunks_by_section.get((source_id, section_name), [])
            for block in media_blocks(section):
                if not linked_chunk_ids:
                    raise ValueError(
                        f"{source_id} / {section_name}: media exists but no approved citation chunk can link it"
                    )
                if block.kind == "image":
                    url = resolve_image_url(collection_url, block.target or "", source_commit=source_commit)
                    display_mode = "inline"
                    license_id = source.license_id
                    attribution = f"{source.publisher}; {source.license_id}"
                else:
                    url = resolve_video_url(block.target or "", block.label)
                    display_mode = "external_embed"
                    license_id = "external-platform-terms"
                    attribution = f"Linked from {source.publisher} official documentation; hosted by YouTube"
                media_id = _media_id(block.kind, url)
                occurrence_key = (media_id, source_id, section_name)
                if occurrence_key in occurrence_keys:
                    continue
                occurrence_keys.add(occurrence_key)
                media_occurrence_count += 1
                occurrence = {
                    "document_id": source_id,
                    "section": section_name,
                    "source_anchor": section.source_anchor,
                }
                title = block.caption or block.alt_text or f"{source.title} {block.kind}"
                if media_id not in items_by_id:
                    items_by_id[media_id] = {
                        "media_id": media_id,
                        "media_type": block.kind,
                        "title": title,
                        "url": url,
                        "alt_text": block.alt_text,
                        "caption": block.caption,
                        "display_mode": display_mode,
                        "license": license_id,
                        "attribution": attribution,
                        "official_verified": True,
                        "source_commit": source_commit,
                        "occurrences": [occurrence],
                    }
                elif occurrence not in items_by_id[media_id]["occurrences"]:
                    items_by_id[media_id]["occurrences"].append(occurrence)
                for chunk_id in linked_chunk_ids:
                    if media_id not in links_by_chunk[chunk_id]:
                        links_by_chunk[chunk_id].append(media_id)

    items = list(items_by_id.values())
    links = [
        {"chunk_id": chunk["chunk_id"], "media_ids": links_by_chunk[chunk["chunk_id"]]}
        for chunk in chunks
        if chunk["chunk_id"] in links_by_chunk
    ]
    linked_media_ids = {media_id for link in links for media_id in link["media_ids"]}
    if linked_media_ids != set(items_by_id):
        raise ValueError("media manifest contains an item without a citation chunk link")

    payload: dict[str, object] = {
        "schema_version": MEDIA_MANIFEST_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "document_manifest": _project_reference(document_manifest_path),
        "document_manifest_checksum": sha256_bytes(document_manifest_path.read_bytes()),
        "source_registry": _project_reference(registry_path),
        "source_registry_checksum": sha256_bytes(registry_path.read_bytes()),
        "source_commit": source_commit,
        "linker_version": MEDIA_LINKER_VERSION,
        "statistics": {
            "media_items": len(items),
            "media_occurrences": media_occurrence_count,
            "linked_chunks": len(links),
            "image_items": sum(item["media_type"] == "image" for item in items),
            "video_items": sum(item["media_type"] == "video" for item in items),
        },
        "items": items,
        "links": links,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chunk-linked official image/video metadata.")
    parser.add_argument("--document-manifest", type=Path, default=DOCUMENT_MANIFEST_PATH)
    parser.add_argument("--source-registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=MEDIA_MANIFEST_PATH)
    args = parser.parse_args()
    payload = build_media_manifest(
        document_manifest_path=args.document_manifest,
        registry_path=args.source_registry,
        raw_root=args.raw_root,
        output_path=args.output,
    )
    stats = payload["statistics"]
    print(
        f"media: {stats['media_items']} unique / {stats['media_occurrences']} occurrences; "
        f"linked chunks: {stats['linked_chunks']}"
    )
    print(f"media manifest: {args.output}")


if __name__ == "__main__":
    main()
