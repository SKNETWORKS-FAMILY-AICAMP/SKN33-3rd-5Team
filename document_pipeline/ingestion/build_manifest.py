"""Parse collected AsciiDoc files and build the reviewed RAG manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

try:  # Supports both `python -m` and direct script execution.
    from .fetch import PIPELINE_ROOT, SourceRecord, included_sources
    from .parse_asciidoc import ParsedSection, anchor_for, parse_asciidoc
except ImportError:  # pragma: no cover - direct invocation path
    from fetch import PIPELINE_ROOT, SourceRecord, included_sources
    from parse_asciidoc import ParsedSection, anchor_for, parse_asciidoc


RAW_ROOT = PIPELINE_ROOT / "data" / "raw"
PROCESSED_ROOT = PIPELINE_ROOT / "data" / "processed"
MANIFEST_PATH = PIPELINE_ROOT / "data" / "manifest.json"
PARSER_VERSION = "asciidoc-basic-1.0.3"
DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 180


def sha256(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def os_versions_for(source: SourceRecord) -> list[str]:
    if "os_installation" in source.tasks or "operating_system" in source.categories:
        return ["Raspberry Pi OS"]
    return []


def split_chunk_text(text: str, *, size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Prefer paragraph boundaries and retain short overlap for retrieval context."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap must be smaller than size")
    paragraphs = [re.sub(r"\s+", " ", item).strip() for item in text.split("\n") if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                end = min(start + size, len(paragraph))
                boundary = paragraph.rfind(". ", start, end)
                if boundary > start + size // 2:
                    end = boundary + 1
                chunk = paragraph[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                if end == len(paragraph):
                    break
                start = end - overlap
            continue
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= size:
            current = candidate
            continue
        chunks.append(current)
        overlap_text = current[-overlap:].strip() if overlap else ""
        current = f"{overlap_text}\n{paragraph}".strip() if overlap_text else paragraph
    if current:
        chunks.append(current)
    return chunks


def _load_collection_ledger(raw_root: Path) -> dict[str, object]:
    ledger_path = raw_root / "collection.json"
    if not ledger_path.exists():
        raise FileNotFoundError("raw collection ledger is missing; run fetch.py first")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != "1.0.0":
        raise ValueError("unsupported raw collection ledger version")
    return ledger


def _ledger_by_source_id(ledger: dict[str, object]) -> dict[str, dict[str, str]]:
    documents = ledger.get("documents")
    if not isinstance(documents, list):
        raise ValueError("collection ledger documents must be a list")
    result: dict[str, dict[str, str]] = {}
    for item in documents:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("source_id", "path", "document_checksum")):
            raise ValueError("collection ledger has an invalid document entry")
        result[item["source_id"]] = item
    return result


def _chunks_for_source(
    source: SourceRecord,
    sections: Iterable[ParsedSection],
    *,
    document_checksum: str,
    collected_at: str,
    document_version: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for section in sections:
        for content in split_chunk_text(section.body, size=chunk_size, overlap=chunk_overlap):
            chunk_index = len(chunks)
            chunks.append(
                {
                    "document_id": source.source_id,
                    "chunk_id": f"{source.source_id}-{chunk_index:03d}",
                    "chunk_index": chunk_index,
                    "title": source.title,
                    "publisher": source.publisher,
                    "section": section.title,
                    "content": content,
                    "source_url": source.official_page_url,
                    "source_anchor": anchor_for(section.title),
                    "language": source.language,
                    "source_type": source.source_type,
                    "published_at": None,
                    "updated_at": None,
                    "collected_at": collected_at,
                    "document_version": document_version,
                    "license": source.license_id,
                    "product_models": source.product_models,
                    "use_cases": source.use_cases,
                    "tasks": source.tasks,
                    "categories": source.categories,
                    "os_versions": os_versions_for(source),
                    "document_checksum": document_checksum,
                    "chunk_checksum": sha256(content),
                    "parser_version": PARSER_VERSION,
                    "official_verified": True,
                    "image_url": None,
                    "video_url": None,
                }
            )
    return chunks


def validate_manifest(payload: dict[str, object]) -> None:
    """Validate the invariants the RAG adapter relies on without extra packages."""
    required_top_level = {"schema_version", "generated_at", "source_registry", "chunks"}
    if set(payload) != required_top_level or payload["schema_version"] != "1.0.0":
        raise ValueError("manifest top-level contract does not match version 1.0.0")
    chunks = payload["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("manifest must contain at least one chunk")
    chunk_ids: set[str] = set()
    expected_fields = {
        "document_id", "chunk_id", "chunk_index", "title", "publisher", "section", "content", "source_url",
        "source_anchor", "language", "source_type", "published_at", "updated_at", "collected_at", "document_version",
        "license", "product_models", "use_cases", "tasks", "categories", "os_versions", "document_checksum",
        "chunk_checksum", "parser_version", "official_verified", "image_url", "video_url",
    }
    for chunk in chunks:
        if not isinstance(chunk, dict) or set(chunk) != expected_fields:
            raise ValueError("manifest chunk fields differ from the canonical contract")
        if chunk["chunk_id"] in chunk_ids:
            raise ValueError(f"duplicate chunk ID: {chunk['chunk_id']}")
        chunk_ids.add(chunk["chunk_id"])
        if not chunk["content"] or chunk["chunk_checksum"] != sha256(chunk["content"]):
            raise ValueError(f"invalid content checksum: {chunk['chunk_id']}")
        if not chunk["official_verified"]:
            raise ValueError(f"unverified source in manifest: {chunk['chunk_id']}")


def build_manifest(
    *,
    raw_root: Path = RAW_ROOT,
    output_path: Path = MANIFEST_PATH,
    processed_root: Path = PROCESSED_ROOT,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, object]:
    """Transform the current raw collection into a static RAG manifest."""
    ledger = _load_collection_ledger(raw_root)
    ledger_by_source = _ledger_by_source_id(ledger)
    collected_at = ledger.get("collected_at")
    commit = ledger.get("commit")
    if not isinstance(collected_at, str) or not isinstance(commit, str):
        raise ValueError("collection ledger is missing collected_at or commit")

    all_chunks: list[dict[str, object]] = []
    parsed_sections: dict[str, list[dict[str, object]]] = {}
    for source in included_sources():
        entry = ledger_by_source.get(source.source_id)
        if entry is None:
            raise ValueError(f"collection ledger does not contain approved source: {source.source_id}")
        raw_path = raw_root / entry["path"]
        raw_bytes = raw_path.read_bytes()
        if sha256(raw_bytes) != entry["document_checksum"]:
            raise ValueError(f"raw file checksum changed after collection: {source.source_id}")
        sections = parse_asciidoc(raw_bytes.decode("utf-8"), fallback_title=source.title)
        parsed_sections[source.source_id] = [
            {"title": section.title, "level": section.level, "body": section.body} for section in sections
        ]
        all_chunks.extend(
            _chunks_for_source(
                source,
                sections,
                document_checksum=entry["document_checksum"],
                collected_at=collected_at,
                document_version=commit,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_registry": "document_pipeline/data/source_registry.csv",
        "chunks": all_chunks,
    }
    validate_manifest(manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    processed_root.mkdir(parents=True, exist_ok=True)
    (processed_root / "parsed_sections.json").write_text(
        json.dumps(parsed_sections, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build PiCare's static RAG manifest from raw AsciiDoc.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    args = parser.parse_args()
    manifest = build_manifest(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print(f"built {len(manifest['chunks'])} chunks")
    print(f"manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
