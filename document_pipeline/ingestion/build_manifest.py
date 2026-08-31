"""Build the static RAG manifest from semantic AsciiDoc sections."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, Protocol, Sequence

from src.contracts.retrieval_text import build_e5_passage

try:  # Supports both `python -m` and direct script execution.
    from .fetch import PIPELINE_ROOT, REGISTRY_PATH, SourceRecord, included_sources, registry_reference
    from .parse_asciidoc import ParsedBlock, ParsedSection, parse_asciidoc, render_block, section_to_dict
except ImportError:  # pragma: no cover - direct invocation path
    from fetch import PIPELINE_ROOT, REGISTRY_PATH, SourceRecord, included_sources, registry_reference
    from parse_asciidoc import ParsedBlock, ParsedSection, parse_asciidoc, render_block, section_to_dict


RAW_ROOT = PIPELINE_ROOT / "data" / "raw"
PROCESSED_ROOT = PIPELINE_ROOT / "data" / "processed"
MANIFEST_PATH = PIPELINE_ROOT / "data" / "manifest.json"
PRODUCT_MEDIA_REGISTRY_PATH = PIPELINE_ROOT / "data" / "product_media_registry.json"
PARSER_VERSION = "asciidoc-semantic-3.0.0"
PIPELINE_VERSION = "document-pipeline-3.0.0"
DEFAULT_TOKENIZER_NAME = "intfloat/multilingual-e5-base"
DEFAULT_TARGET_TOKENS = 360
DEFAULT_MAX_TOKENS = 460
DEFAULT_OVERLAP_TOKENS = 60
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
UNRESOLVED_ATTRIBUTE = re.compile(r"\{[A-Za-z][A-Za-z0-9_-]*\}")
DESCRIPTION_LABEL = re.compile(r"(?m)^\S.*::$")
BLOCK_TITLE_RESIDUE = re.compile(r"(?m)^\.[A-Za-z]")
TAB_DELIMITER_RESIDUE = re.compile(r"(?m)^={6}$")
STANDALONE_CONTINUATION = re.compile(r"(?m)^\+$")
IMAGE_MACRO_RESIDUE = re.compile(r"(?m)^image::")


class Tokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool = True) -> Sequence[int]: ...


@dataclass(frozen=True)
class ChunkUnit:
    block: ParsedBlock
    text: str
    quality_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    quality_issues: tuple[str, ...] = ()


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
    """Count one complete E5 input, including model special tokens."""
    return len(tokenizer.encode(text, add_special_tokens=True))


def os_versions_for(source: SourceRecord) -> list[str]:
    if "os_installation" in source.tasks or "operating_system" in source.categories:
        return ["Raspberry Pi OS"]
    return []


@lru_cache(maxsize=1)
def approved_product_models(path: Path = PRODUCT_MEDIA_REGISTRY_PATH) -> tuple[str, ...]:
    """Read only product names already reviewed in the media/product registry."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    models = tuple(item["product_model"] for item in payload["items"])
    if len(models) != len(set(models)) or not all(isinstance(model, str) and model for model in models):
        raise ValueError("product media registry contains invalid product model names")
    return models


def product_models_for(content: str, explicit_models: Sequence[str] = ()) -> list[str]:
    """Tag exact, curated model names without asking an LLM to infer products."""

    curated = approved_product_models()
    matched = set(explicit_models)
    for model in curated:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(model)}(?![A-Za-z0-9+])"
        if re.search(pattern, content, flags=re.IGNORECASE):
            matched.add(model)
    return [model for model in curated if model in matched] + sorted(matched - set(curated))


def _text_quality_issues(text: str) -> tuple[str, ...]:
    checks = (
        (UNRESOLVED_ATTRIBUTE, "unresolved_asciidoc_attribute"),
        (DESCRIPTION_LABEL, "unparsed_description_label"),
        (BLOCK_TITLE_RESIDUE, "unparsed_block_title"),
        (TAB_DELIMITER_RESIDUE, "unparsed_tab_delimiter"),
        (STANDALONE_CONTINUATION, "unparsed_continuation_marker"),
        (IMAGE_MACRO_RESIDUE, "unparsed_image_macro"),
    )
    return tuple(reason for pattern, reason in checks if pattern.search(text))


def block_quality_issues(block: ParsedBlock) -> tuple[str, ...]:
    """Inspect parsed fields while deliberately excluding literal code content."""

    issues = list(block.issues)
    texts: list[str] = []
    if block.kind in {"paragraph", "admonition"}:
        texts.append(block.text)
    elif block.kind == "list":
        texts.extend(item.text for item in block.items)
    elif block.kind == "table":
        texts.extend(block.headers)
        texts.extend(cell for row in block.rows for cell in row)
        if block.caption:
            texts.append(block.caption)
    elif block.kind == "image":
        texts.extend(value for value in (block.alt_text, block.caption) if value)
    elif block.kind == "tab":
        if block.label:
            texts.append(block.label)
        if block.text:
            texts.append(block.text)
        for child in block.blocks:
            issues.extend(block_quality_issues(child))
    for text in texts:
        issues.extend(_text_quality_issues(text))
    return tuple(dict.fromkeys(issues))


def _paragraph_units(
    block: ParsedBlock,
    count_tokens: Callable[[str], int],
    max_tokens: int,
) -> list[ChunkUnit]:
    sentences = [sentence.strip() for sentence in SENTENCE_BOUNDARY.split(block.text) if sentence.strip()]
    if not sentences:
        return []
    units: list[ChunkUnit] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*current, sentence])
        if current and count_tokens(candidate) > max_tokens:
            text = " ".join(current)
            units.append(ChunkUnit(ParsedBlock(kind="paragraph", text=text), text, block_quality_issues(block)))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        text = " ".join(current)
        if count_tokens(text) > max_tokens:
            # A single very long sentence is split only at word boundaries.
            words = text.split()
            segment: list[str] = []
            for word in words:
                candidate = " ".join([*segment, word])
                if segment and count_tokens(candidate) > max_tokens:
                    rendered = " ".join(segment)
                    units.append(
                        ChunkUnit(
                            ParsedBlock(kind="paragraph", text=rendered),
                            rendered,
                            block_quality_issues(block),
                        )
                    )
                    segment = [word]
                else:
                    segment.append(word)
            if segment:
                rendered = " ".join(segment)
                units.append(
                    ChunkUnit(
                        ParsedBlock(kind="paragraph", text=rendered),
                        rendered,
                        block_quality_issues(block),
                    )
                )
        else:
            units.append(ChunkUnit(ParsedBlock(kind="paragraph", text=text), text, block_quality_issues(block)))
    return units


def _line_units(block: ParsedBlock, count_tokens: Callable[[str], int], max_tokens: int) -> list[ChunkUnit]:
    """Split oversized code blocks only between complete source lines."""
    lines = block.text.splitlines()
    units: list[ChunkUnit] = []
    current: list[str] = []
    for line in lines:
        candidate_block = ParsedBlock(kind="code", text="\n".join([*current, line]), language=block.language)
        if current and count_tokens(render_block(candidate_block)) > max_tokens:
            completed = ParsedBlock(kind="code", text="\n".join(current), language=block.language)
            units.append(ChunkUnit(completed, render_block(completed), block.issues))
            current = [line]
        else:
            current.append(line)
    if current:
        completed = ParsedBlock(kind="code", text="\n".join(current), language=block.language)
        units.append(ChunkUnit(completed, render_block(completed), block.issues))
    return units


def _list_units(block: ParsedBlock, count_tokens: Callable[[str], int], max_tokens: int) -> list[ChunkUnit]:
    units: list[ChunkUnit] = []
    current = []
    for item in block.items:
        candidate = ParsedBlock(kind="list", ordered=block.ordered, items=tuple([*current, item]))
        if current and count_tokens(render_block(candidate)) > max_tokens:
            completed = ParsedBlock(kind="list", ordered=block.ordered, items=tuple(current))
            units.append(ChunkUnit(completed, render_block(completed), block_quality_issues(block)))
            current = [item]
        else:
            current.append(item)
    if current:
        completed = ParsedBlock(kind="list", ordered=block.ordered, items=tuple(current))
        units.append(ChunkUnit(completed, render_block(completed), block_quality_issues(block)))
    return units


def _table_units(block: ParsedBlock, count_tokens: Callable[[str], int], max_tokens: int) -> list[ChunkUnit]:
    units: list[ChunkUnit] = []
    current: list[tuple[str, ...]] = []
    for row in block.rows:
        candidate = ParsedBlock(kind="table", headers=block.headers, rows=tuple([*current, row]), caption=block.caption)
        if current and count_tokens(render_block(candidate)) > max_tokens:
            completed = ParsedBlock(kind="table", headers=block.headers, rows=tuple(current), caption=block.caption)
            units.append(ChunkUnit(completed, render_block(completed), block_quality_issues(block)))
            current = [row]
        else:
            current.append(row)
    if current or block.headers:
        completed = ParsedBlock(kind="table", headers=block.headers, rows=tuple(current), caption=block.caption)
        units.append(ChunkUnit(completed, render_block(completed), block_quality_issues(block)))
    return units


def split_block(block: ParsedBlock, count_tokens: Callable[[str], int], max_tokens: int) -> list[ChunkUnit]:
    """Split only inside a block when a whole semantic unit exceeds the hard limit."""
    rendered = render_block(block)
    if count_tokens(rendered) <= max_tokens:
        return [ChunkUnit(block, rendered, block_quality_issues(block))]
    if block.kind == "paragraph":
        return _paragraph_units(block, count_tokens, max_tokens)
    if block.kind == "code":
        return _line_units(block, count_tokens, max_tokens)
    if block.kind == "list":
        return _list_units(block, count_tokens, max_tokens)
    if block.kind == "table":
        return _table_units(block, count_tokens, max_tokens)
    if block.kind == "admonition":
        lines = [line for line in block.text.splitlines() if line.strip()]
        paragraph = ParsedBlock(kind="paragraph", text=" ".join(lines))
        return [
            ChunkUnit(
                ParsedBlock(kind="admonition", severity=block.severity, text=unit.text),
                render_block(ParsedBlock(kind="admonition", severity=block.severity, text=unit.text)),
                block_quality_issues(block),
            )
            for unit in _paragraph_units(paragraph, count_tokens, max_tokens)
        ]
    if block.kind == "tab":
        units: list[ChunkUnit] = []
        for child in block.blocks:
            for child_unit in split_block(child, count_tokens, max_tokens):
                tab = ParsedBlock(kind="tab", label=block.label, blocks=(child_unit.block,), issues=block.issues)
                units.append(
                    ChunkUnit(
                        tab,
                        render_block(tab),
                        tuple(dict.fromkeys((*block_quality_issues(block), *child_unit.quality_issues))),
                    )
                )
        return units or [ChunkUnit(block, rendered, block_quality_issues(block))]
    return [ChunkUnit(block, rendered, block_quality_issues(block))]


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


def chunk_section_drafts(
    section: ParsedSection,
    *,
    tokenizer: Tokenizer,
    document_title: str | None = None,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Chunk semantic units while counting the complete E5 passage input."""
    if not 0 < target_tokens <= max_tokens:
        raise ValueError("target token count must be positive and no greater than max token count")
    if overlap_tokens < 0:
        raise ValueError("overlap token count cannot be negative")
    title = document_title or section.heading_path[0]
    section_name = " > ".join(section.heading_path)

    def count_content(content: str) -> int:
        passage = build_e5_passage(title=title, section=section_name, content=content)
        return token_count(tokenizer, passage)

    units = [unit for block in section.blocks for unit in split_block(block, count_content, max_tokens)]
    chunks: list[ChunkDraft] = []
    current: list[ChunkUnit] = []

    def append_current() -> None:
        content = _render_units(current)
        issue_values = [issue for unit in current for issue in unit.quality_issues]
        if count_content(content) > max_tokens:
            issue_values.append("embedding_input_exceeds_hard_token_limit")
        issues = tuple(dict.fromkeys(issue_values))
        chunks.append(ChunkDraft(content=content, quality_issues=issues))

    for unit in units:
        if not current:
            current = [unit]
            continue
        candidate = _render_units([*current, unit])
        if count_content(candidate) <= target_tokens:
            current.append(unit)
            continue
        if count_content(candidate) <= max_tokens and count_content(_render_units(current)) < target_tokens // 2:
            current.append(unit)
            continue
        append_current()
        overlap = _overlap_unit(current, tokenizer, overlap_tokens)
        current = [unit] if overlap is None else [overlap, unit]
        if count_content(_render_units(current)) > max_tokens:
            current = [unit]
    if current:
        append_current()
    return chunks


def chunk_section(
    section: ParsedSection,
    *,
    tokenizer: Tokenizer,
    document_title: str | None = None,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[str]:
    """Compatibility wrapper returning citation text only."""

    return [
        draft.content
        for draft in chunk_section_drafts(
            section,
            tokenizer=tokenizer,
            document_title=document_title,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
    ]


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
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    approved: list[dict[str, object]] = []
    review_items: list[dict[str, object]] = []
    chunk_index = 0
    for section in sections:
        section_name = " > ".join(section.heading_path)
        for draft in chunk_section_drafts(
            section,
            tokenizer=tokenizer,
            document_title=source.title,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        ):
            chunk_id = f"{source.source_id}-{chunk_index:03d}"
            chunk_index += 1
            product_models = product_models_for(
                f"{section_name}\n{draft.content}",
                source.product_models,
            )
            base = {
                "document_id": source.source_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index - 1,
                "title": source.title,
                "section": section_name,
                "content": draft.content,
                "source_url": source.official_page_url,
                "source_anchor": section.source_anchor,
                "chunk_checksum": sha256(draft.content),
            }
            if draft.quality_issues:
                review_items.append(
                    {
                        **base,
                        "quality_status": "needs_review",
                        "review_reasons": list(draft.quality_issues),
                    }
                )
                continue
            approved.append(
                {
                    "document_id": source.source_id,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index - 1,
                    "title": source.title,
                    "publisher": source.publisher,
                    "section": section_name,
                    "content": draft.content,
                    "source_url": source.official_page_url,
                    "source_anchor": section.source_anchor,
                    "language": source.language,
                    "source_type": source.source_type,
                    "published_at": None,
                    "updated_at": None,
                    "collected_at": collected_at,
                    "document_version": document_version,
                    "license": source.license_id,
                    "product_models": product_models,
                    "use_cases": source.use_cases,
                    "tasks": source.tasks,
                    "categories": source.categories,
                    "os_versions": os_versions_for(source),
                    "document_checksum": document_checksum,
                    "chunk_checksum": sha256(draft.content),
                    "embedding_checksum": sha256(
                        build_e5_passage(title=source.title, section=section_name, content=draft.content)
                    ),
                    "parser_version": PARSER_VERSION,
                    "official_verified": source.official_verified,
                    "quality_status": "approved",
                    "image_url": None,
                    "video_url": None,
                }
            )
    return approved, review_items


def _tokenizer_revision(tokenizer: Tokenizer, explicit_revision: str | None) -> str:
    if explicit_revision:
        return explicit_revision
    init_kwargs = getattr(tokenizer, "init_kwargs", {})
    if isinstance(init_kwargs, dict) and isinstance(init_kwargs.get("_commit_hash"), str):
        return init_kwargs["_commit_hash"]
    name_or_path = getattr(tokenizer, "name_or_path", None)
    if isinstance(name_or_path, str) and name_or_path:
        return name_or_path
    return f"{type(tokenizer).__module__}.{type(tokenizer).__qualname__}"


def _processing_metadata(
    *,
    registry_path: Path,
    tokenizer_name: str,
    tokenizer_revision: str,
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> dict[str, object]:
    config: dict[str, object] = {
        "pipeline_version": PIPELINE_VERSION,
        "parser_version": PARSER_VERSION,
        "tokenizer_name": tokenizer_name,
        "tokenizer_revision": tokenizer_revision,
        "target_tokens": target_tokens,
        "max_tokens": max_tokens,
        "overlap_tokens": overlap_tokens,
        "source_registry_checksum": sha256(registry_path.read_bytes()),
        "product_registry_checksum": sha256(PRODUCT_MEDIA_REGISTRY_PATH.read_bytes()),
    }
    config["config_fingerprint"] = sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return config


def _shingles(content: str, width: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", content.casefold())
    if len(words) < max(20, width):
        return set()
    return {tuple(words[index : index + width]) for index in range(len(words) - width + 1)}


def _near_duplicate_pairs(chunks: list[dict[str, object]], threshold: float = 0.9) -> list[dict[str, object]]:
    shingle_sets = [_shingles(str(chunk["content"])) for chunk in chunks]
    pairs: list[dict[str, object]] = []
    for left_index, left in enumerate(chunks):
        left_shingles = shingle_sets[left_index]
        if not left_shingles:
            continue
        for right_index in range(left_index + 1, len(chunks)):
            right_shingles = shingle_sets[right_index]
            if not right_shingles:
                continue
            similarity = len(left_shingles & right_shingles) / len(left_shingles | right_shingles)
            if similarity >= threshold:
                pairs.append(
                    {
                        "left_chunk_id": left["chunk_id"],
                        "right_chunk_id": chunks[right_index]["chunk_id"],
                        "jaccard_similarity": round(similarity, 4),
                        "quality_status": "needs_review",
                    }
                )
    return pairs


def _remove_exact_duplicates(
    chunks: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    unique: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    first_by_checksum: dict[object, str] = {}
    for chunk in chunks:
        checksum = chunk["chunk_checksum"]
        duplicate_of = first_by_checksum.get(checksum)
        if duplicate_of is None:
            first_by_checksum[checksum] = str(chunk["chunk_id"])
            unique.append(chunk)
            continue
        rejected.append(
            {
                "document_id": chunk["document_id"],
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "title": chunk["title"],
                "section": chunk["section"],
                "content": chunk["content"],
                "source_url": chunk["source_url"],
                "source_anchor": chunk["source_anchor"],
                "chunk_checksum": checksum,
                "quality_status": "rejected",
                "review_reasons": [f"exact_duplicate_of:{duplicate_of}"],
            }
        )
    return unique, rejected


def validate_manifest(payload: dict[str, object]) -> None:
    """Validate the invariants the RAG adapter relies on without extra packages."""
    required_top_level = {"schema_version", "generated_at", "source_registry", "processing", "chunks"}
    if set(payload) != required_top_level or payload["schema_version"] != "1.1.0":
        raise ValueError("manifest top-level contract does not match version 1.1.0")
    processing = payload["processing"]
    if not isinstance(processing, dict):
        raise ValueError("manifest processing metadata must be an object")
    processing_fields = {
        "pipeline_version",
        "parser_version",
        "tokenizer_name",
        "tokenizer_revision",
        "target_tokens",
        "max_tokens",
        "overlap_tokens",
        "source_registry_checksum",
        "product_registry_checksum",
        "config_fingerprint",
    }
    if set(processing) != processing_fields:
        raise ValueError("manifest processing metadata fields differ from version 1.1.0")
    if not 0 < processing["target_tokens"] <= processing["max_tokens"]:
        raise ValueError("manifest processing token limits are invalid")
    fingerprint = processing.get("config_fingerprint")
    fingerprint_input = {key: value for key, value in processing.items() if key != "config_fingerprint"}
    if fingerprint != sha256(json.dumps(fingerprint_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))):
        raise ValueError("manifest processing config fingerprint is invalid")
    chunks = payload["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("manifest must contain at least one chunk")
    chunk_ids: set[str] = set()
    chunk_checksums: set[str] = set()
    expected_fields = {
        "document_id", "chunk_id", "chunk_index", "title", "publisher", "section", "content", "source_url",
        "source_anchor", "language", "source_type", "published_at", "updated_at", "collected_at", "document_version",
        "license", "product_models", "use_cases", "tasks", "categories", "os_versions", "document_checksum",
        "chunk_checksum", "embedding_checksum", "parser_version", "official_verified", "quality_status",
        "image_url", "video_url",
    }
    for chunk in chunks:
        if not isinstance(chunk, dict) or set(chunk) != expected_fields:
            raise ValueError("manifest chunk fields differ from the canonical contract")
        if chunk["chunk_id"] in chunk_ids:
            raise ValueError(f"duplicate chunk ID: {chunk['chunk_id']}")
        chunk_ids.add(chunk["chunk_id"])
        if not chunk["content"] or chunk["chunk_checksum"] != sha256(chunk["content"]):
            raise ValueError(f"invalid content checksum: {chunk['chunk_id']}")
        if chunk["chunk_checksum"] in chunk_checksums:
            raise ValueError(f"duplicate content checksum: {chunk['chunk_id']}")
        chunk_checksums.add(chunk["chunk_checksum"])
        expected_embedding_checksum = sha256(
            build_e5_passage(title=chunk["title"], section=chunk["section"], content=chunk["content"])
        )
        if chunk["embedding_checksum"] != expected_embedding_checksum:
            raise ValueError(f"invalid embedding checksum: {chunk['chunk_id']}")
        if chunk["source_anchor"] is not None and not isinstance(chunk["source_anchor"], str):
            raise ValueError(f"invalid source anchor: {chunk['chunk_id']}")
        if chunk["official_verified"] is not True:
            raise ValueError(f"unverified source in manifest: {chunk['chunk_id']}")
        if chunk["quality_status"] != "approved":
            raise ValueError(f"unapproved chunk in manifest: {chunk['chunk_id']}")


def build_manifest(
    *,
    raw_root: Path = RAW_ROOT,
    output_path: Path = MANIFEST_PATH,
    processed_root: Path = PROCESSED_ROOT,
    tokenizer: Tokenizer | None = None,
    tokenizer_name: str = DEFAULT_TOKENIZER_NAME,
    tokenizer_revision: str | None = None,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, object]:
    """Transform the current raw collection into a token-aware static RAG manifest."""
    registry_path = registry_path.resolve()
    tokenizer = tokenizer or load_e5_tokenizer(tokenizer_name)
    resolved_tokenizer_revision = _tokenizer_revision(tokenizer, tokenizer_revision)
    ledger = _load_collection_ledger(raw_root)
    ledger_by_source = _ledger_by_source_id(ledger)
    collected_at = ledger.get("collected_at")
    commit = ledger.get("commit")
    if not isinstance(collected_at, str) or not isinstance(commit, str):
        raise ValueError("collection ledger is missing collected_at or commit")

    all_chunks: list[dict[str, object]] = []
    review_items: list[dict[str, object]] = []
    parsed_sections: dict[str, list[dict[str, object]]] = {}
    for source in included_sources(registry_path):
        entry = ledger_by_source.get(source.source_id)
        if entry is None:
            raise ValueError(f"collection ledger does not contain approved source: {source.source_id}")
        raw_path = raw_root / entry["path"]
        raw_bytes = raw_path.read_bytes()
        if sha256(raw_bytes) != entry["document_checksum"]:
            raise ValueError(f"raw file checksum changed after collection: {source.source_id}")
        sections = parse_asciidoc(raw_bytes.decode("utf-8"), fallback_title=source.title)
        parsed_sections[source.source_id] = [section_to_dict(section) for section in sections]
        approved, needs_review = _chunks_for_source(
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
        all_chunks.extend(approved)
        review_items.extend(needs_review)

    all_chunks, exact_duplicates = _remove_exact_duplicates(all_chunks)
    review_items.extend(exact_duplicates)
    processing = _processing_metadata(
        registry_path=registry_path,
        tokenizer_name=tokenizer_name,
        tokenizer_revision=resolved_tokenizer_revision,
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    generated_at = datetime.now(UTC).isoformat()

    manifest: dict[str, object] = {
        "schema_version": "1.1.0",
        "generated_at": generated_at,
        "source_registry": registry_reference(registry_path),
        "processing": processing,
        "chunks": all_chunks,
    }
    validate_manifest(manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    processed_root.mkdir(parents=True, exist_ok=True)
    (processed_root / "parsed_sections.json").write_text(
        json.dumps(parsed_sections, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    qa_report = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "quality_gate": "only approved chunks are written to manifest.json",
        "items": review_items,
        "near_duplicate_pairs": _near_duplicate_pairs(all_chunks),
    }
    (processed_root / "qa_report.json").write_text(
        json.dumps(qa_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build PiCare's token-aware RAG manifest from raw AsciiDoc.")
    parser.add_argument("--tokenizer-name", default=DEFAULT_TOKENIZER_NAME)
    parser.add_argument("--tokenizer-revision")
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    args = parser.parse_args()
    manifest = build_manifest(
        tokenizer_name=args.tokenizer_name,
        tokenizer_revision=args.tokenizer_revision,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    print(f"built {len(manifest['chunks'])} chunks")
    print(f"manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
