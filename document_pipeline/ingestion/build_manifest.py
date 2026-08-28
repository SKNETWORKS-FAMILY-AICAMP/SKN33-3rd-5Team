"""Build the static RAG manifest from semantic AsciiDoc sections."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Sequence

try:  # Supports both `python -m` and direct script execution.
    from .fetch import PIPELINE_ROOT, SourceRecord, included_sources
    from .parse_asciidoc import ParsedBlock, ParsedSection, parse_asciidoc, render_block, section_to_dict
except ImportError:  # pragma: no cover - direct invocation path
    from fetch import PIPELINE_ROOT, SourceRecord, included_sources
    from parse_asciidoc import ParsedBlock, ParsedSection, parse_asciidoc, render_block, section_to_dict


RAW_ROOT = PIPELINE_ROOT / "data" / "raw"
PROCESSED_ROOT = PIPELINE_ROOT / "data" / "processed"
MANIFEST_PATH = PIPELINE_ROOT / "data" / "manifest.json"
PARSER_VERSION = "asciidoc-semantic-2.0.0"
DEFAULT_TOKENIZER_NAME = "intfloat/multilingual-e5-base"
DEFAULT_TARGET_TOKENS = 360
DEFAULT_MAX_TOKENS = 460
DEFAULT_OVERLAP_TOKENS = 60
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class Tokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool = True) -> Sequence[int]: ...


@dataclass(frozen=True)
class ChunkUnit:
    block: ParsedBlock
    text: str


def sha256(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def load_e5_tokenizer(name: str = DEFAULT_TOKENIZER_NAME) -> Tokenizer:
    """Load the same tokenizer used by multilingual-e5-base embeddings."""
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - dependency is declared in requirements.txt
        raise RuntimeError("transformers is required for token-aware chunking; install requirements.txt") from exc
    return AutoTokenizer.from_pretrained(name, use_fast=True)


def token_count(tokenizer: Tokenizer, text: str) -> int:
    """Count exactly what E5 receives, including its required passage prefix."""
    return len(tokenizer.encode(f"passage: {text}", add_special_tokens=True))


def os_versions_for(source: SourceRecord) -> list[str]:
    if "os_installation" in source.tasks or "operating_system" in source.categories:
        return ["Raspberry Pi OS"]
    return []


def _paragraph_units(block: ParsedBlock, tokenizer: Tokenizer, max_tokens: int) -> list[ChunkUnit]:
    sentences = [sentence.strip() for sentence in SENTENCE_BOUNDARY.split(block.text) if sentence.strip()]
    if not sentences:
        return []
    units: list[ChunkUnit] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*current, sentence])
        if current and token_count(tokenizer, candidate) > max_tokens:
            text = " ".join(current)
            units.append(ChunkUnit(ParsedBlock(kind="paragraph", text=text), text))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        text = " ".join(current)
        if token_count(tokenizer, text) > max_tokens:
            # A single very long sentence is split only at word boundaries.
            words = text.split()
            segment: list[str] = []
            for word in words:
                candidate = " ".join([*segment, word])
                if segment and token_count(tokenizer, candidate) > max_tokens:
                    rendered = " ".join(segment)
                    units.append(ChunkUnit(ParsedBlock(kind="paragraph", text=rendered), rendered))
                    segment = [word]
                else:
                    segment.append(word)
            if segment:
                rendered = " ".join(segment)
                units.append(ChunkUnit(ParsedBlock(kind="paragraph", text=rendered), rendered))
        else:
            units.append(ChunkUnit(ParsedBlock(kind="paragraph", text=text), text))
    return units


def _line_units(block: ParsedBlock, tokenizer: Tokenizer, max_tokens: int) -> list[ChunkUnit]:
    """Split oversized code blocks only between complete source lines."""
    lines = block.text.splitlines()
    units: list[ChunkUnit] = []
    current: list[str] = []
    for line in lines:
        candidate_block = ParsedBlock(kind="code", text="\n".join([*current, line]), language=block.language)
        if current and token_count(tokenizer, render_block(candidate_block)) > max_tokens:
            completed = ParsedBlock(kind="code", text="\n".join(current), language=block.language)
            units.append(ChunkUnit(completed, render_block(completed)))
            current = [line]
        else:
            current.append(line)
    if current:
        completed = ParsedBlock(kind="code", text="\n".join(current), language=block.language)
        units.append(ChunkUnit(completed, render_block(completed)))
    return units


def _list_units(block: ParsedBlock, tokenizer: Tokenizer, max_tokens: int) -> list[ChunkUnit]:
    units: list[ChunkUnit] = []
    current = []
    for item in block.items:
        candidate = ParsedBlock(kind="list", ordered=block.ordered, items=tuple([*current, item]))
        if current and token_count(tokenizer, render_block(candidate)) > max_tokens:
            completed = ParsedBlock(kind="list", ordered=block.ordered, items=tuple(current))
            units.append(ChunkUnit(completed, render_block(completed)))
            current = [item]
        else:
            current.append(item)
    if current:
        completed = ParsedBlock(kind="list", ordered=block.ordered, items=tuple(current))
        units.append(ChunkUnit(completed, render_block(completed)))
    return units


def _table_units(block: ParsedBlock, tokenizer: Tokenizer, max_tokens: int) -> list[ChunkUnit]:
    units: list[ChunkUnit] = []
    current: list[tuple[str, ...]] = []
    for row in block.rows:
        candidate = ParsedBlock(kind="table", headers=block.headers, rows=tuple([*current, row]))
        if current and token_count(tokenizer, render_block(candidate)) > max_tokens:
            completed = ParsedBlock(kind="table", headers=block.headers, rows=tuple(current))
            units.append(ChunkUnit(completed, render_block(completed)))
            current = [row]
        else:
            current.append(row)
    if current or block.headers:
        completed = ParsedBlock(kind="table", headers=block.headers, rows=tuple(current))
        units.append(ChunkUnit(completed, render_block(completed)))
    return units


def split_block(block: ParsedBlock, tokenizer: Tokenizer, max_tokens: int) -> list[ChunkUnit]:
    """Split only inside a block when a whole semantic unit exceeds the hard limit."""
    rendered = render_block(block)
    if token_count(tokenizer, rendered) <= max_tokens:
        return [ChunkUnit(block, rendered)]
    if block.kind == "paragraph":
        return _paragraph_units(block, tokenizer, max_tokens)
    if block.kind == "code":
        return _line_units(block, tokenizer, max_tokens)
    if block.kind == "list":
        return _list_units(block, tokenizer, max_tokens)
    if block.kind == "table":
        return _table_units(block, tokenizer, max_tokens)
    if block.kind == "admonition":
        lines = [line for line in block.text.splitlines() if line.strip()]
        paragraph = ParsedBlock(kind="paragraph", text=" ".join(lines))
        return [
            ChunkUnit(
                ParsedBlock(kind="admonition", severity=block.severity, text=unit.text),
                render_block(ParsedBlock(kind="admonition", severity=block.severity, text=unit.text)),
            )
            for unit in _paragraph_units(paragraph, tokenizer, max_tokens)
        ]
    return [ChunkUnit(block, rendered)]


def _render_units(units: list[ChunkUnit]) -> str:
    return "\n\n".join(unit.text for unit in units)


def _overlap_unit(units: list[ChunkUnit], tokenizer: Tokenizer, overlap_tokens: int) -> ChunkUnit | None:
    """Reuse one complete narrative block; never splice a word or code line."""
    if not units:
        return None
    candidate = units[-1]
    if candidate.block.kind in {"code", "table", "image"}:
        return None
    return candidate if token_count(tokenizer, candidate.text) <= overlap_tokens else None


def chunk_section(
    section: ParsedSection,
    *,
    tokenizer: Tokenizer,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[str]:
    """Chunk semantic units around E5 token limits without string-slice overlap."""
    if not 0 < target_tokens <= max_tokens:
        raise ValueError("target token count must be positive and no greater than max token count")
    if overlap_tokens < 0:
        raise ValueError("overlap token count cannot be negative")
    units = [unit for block in section.blocks for unit in split_block(block, tokenizer, max_tokens)]
    chunks: list[str] = []
    current: list[ChunkUnit] = []
    for unit in units:
        if not current:
            current = [unit]
            continue
        candidate = _render_units([*current, unit])
        if token_count(tokenizer, candidate) <= target_tokens:
            current.append(unit)
            continue
        if token_count(tokenizer, candidate) <= max_tokens and token_count(tokenizer, _render_units(current)) < target_tokens // 2:
            current.append(unit)
            continue
        chunks.append(_render_units(current))
        overlap = _overlap_unit(current, tokenizer, overlap_tokens)
        current = [unit] if overlap is None else [overlap, unit]
        if token_count(tokenizer, _render_units(current)) > max_tokens:
            current = [unit]
    if current:
        chunks.append(_render_units(current))
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
    sections: list[ParsedSection],
    *,
    tokenizer: Tokenizer,
    document_checksum: str,
    collected_at: str,
    document_version: str,
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for section in sections:
        for content in chunk_section(
            section,
            tokenizer=tokenizer,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        ):
            chunk_index = len(chunks)
            chunks.append(
                {
                    "document_id": source.source_id,
                    "chunk_id": f"{source.source_id}-{chunk_index:03d}",
                    "chunk_index": chunk_index,
                    "title": source.title,
                    "publisher": source.publisher,
                    "section": " > ".join(section.heading_path),
                    "content": content,
                    "source_url": source.official_page_url,
                    "source_anchor": section.source_anchor,
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
                    "official_verified": source.official_verified,
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
        if chunk["source_anchor"] is not None and not isinstance(chunk["source_anchor"], str):
            raise ValueError(f"invalid source anchor: {chunk['chunk_id']}")
        if chunk["official_verified"] is not True:
            raise ValueError(f"unverified source in manifest: {chunk['chunk_id']}")


def build_manifest(
    *,
    raw_root: Path = RAW_ROOT,
    output_path: Path = MANIFEST_PATH,
    processed_root: Path = PROCESSED_ROOT,
    tokenizer: Tokenizer | None = None,
    tokenizer_name: str = DEFAULT_TOKENIZER_NAME,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> dict[str, object]:
    """Transform the current raw collection into a token-aware static RAG manifest."""
    tokenizer = tokenizer or load_e5_tokenizer(tokenizer_name)
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
        parsed_sections[source.source_id] = [section_to_dict(section) for section in sections]
        all_chunks.extend(
            _chunks_for_source(
                source,
                sections,
                tokenizer=tokenizer,
                document_checksum=entry["document_checksum"],
                collected_at=collected_at,
                document_version=commit,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
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
    parser = argparse.ArgumentParser(description="Build PiCare's token-aware RAG manifest from raw AsciiDoc.")
    parser.add_argument("--tokenizer-name", default=DEFAULT_TOKENIZER_NAME)
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    args = parser.parse_args()
    manifest = build_manifest(
        tokenizer_name=args.tokenizer_name,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    print(f"built {len(manifest['chunks'])} chunks")
    print(f"manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
