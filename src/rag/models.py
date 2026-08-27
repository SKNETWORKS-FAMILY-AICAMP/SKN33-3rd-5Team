"""Public data contracts shared with the document, sLLM, and chatbot modules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagFilters:
    """Search constraints produced by the integration layer from sLLM condition JSON."""

    product_models: tuple[str, ...] = ()
    use_cases: tuple[str, ...] = ()
    os_versions: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    official_only: bool = True


@dataclass(frozen=True)
class DocumentChunk:
    """Validated document/data-team manifest record accepted by the RAG module."""

    chunk_id: str
    document_id: str
    title: str
    section: str
    content: str
    source_url: str
    retrieved_at: str
    document_version: str | None
    license: str
    product_models: tuple[str, ...] = ()
    use_cases: tuple[str, ...] = ()
    os_versions: tuple[str, ...] = ()
    source_type: str = "documentation"
    official_verified: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentChunk":
        normalized = dict(value)
        for key in ("product_models", "use_cases", "os_versions"):
            normalized[key] = tuple(normalized.get(key, ()))
        return cls(**normalized)


@dataclass(frozen=True)
class RagResult:
    """Citation-safe result returned to the chatbot layer."""

    rank: int
    content: str
    chunk_id: str
    document_id: str
    title: str
    section: str
    source_url: str
    license: str
    retrieved_at: str
    document_version: str | None

    @classmethod
    def from_chunk(cls, chunk: DocumentChunk, rank: int) -> "RagResult":
        return cls(
            rank=rank,
            content=chunk.content,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            title=chunk.title,
            section=chunk.section,
            source_url=chunk.source_url,
            license=chunk.license,
            retrieved_at=chunk.retrieved_at,
            document_version=chunk.document_version,
        )
