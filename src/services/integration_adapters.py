"""Pure adapters between the current sLLM, RAG, and shared contracts.

This module intentionally does not modify or import service implementations. It
can be replaced at the integration boundary after teammate-owned result formats
are finalized.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Mapping, Sequence

from src.contracts import ConditionPayload, SearchResponse
from src.rag import RagFilters, RagResult


RetrievalMethod = Literal["dense", "bm25", "hybrid"]


class IntegrationAdapterError(ValueError):
    """Raised when a source object lacks data required by the shared contract."""


@dataclass(frozen=True)
class RagResultMetadata:
    """Metadata required by SearchResponse but absent from the current RagResult."""

    chunk_index: int
    publisher: str
    language: str
    source_type: str
    indexed_at: datetime
    document_checksum: str
    chunk_checksum: str
    embedding_checksum: str
    parser_version: str
    official_verified: bool
    quality_status: str
    source_anchor: str | None = None
    published_at: date | None = None
    updated_at: date | None = None
    product_models: tuple[str, ...] = ()
    use_cases: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    os_versions: tuple[str, ...] = ()
    image_url: str | None = None
    video_url: str | None = None


def condition_payload_to_rag_filters(conditions: ConditionPayload) -> RagFilters:
    """Convert canonical extracted conditions without guessing absent filters."""

    return RagFilters(
        product_models=tuple(conditions.product_models or ()),
        use_cases=(conditions.use_case,) if conditions.use_case else (),
        os_versions=tuple(conditions.os_versions or ()),
        source_types=(),
        official_only=True,
    )


def _collected_at(retrieved_at: str) -> date:
    """Convert the RAG prototype's retrieved_at field to canonical collected_at."""

    normalized = retrieved_at.strip()
    if not normalized:
        raise IntegrationAdapterError("RagResult.retrieved_at이 비어 있습니다.")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise IntegrationAdapterError(
                f"retrieved_at을 collected_at으로 변환할 수 없습니다: {retrieved_at}"
            ) from exc


def rag_results_to_search_response(
    results: Sequence[RagResult],
    *,
    query_id: str,
    query_language: str,
    retrieval_method: RetrievalMethod,
    top_k: int,
    applied_filters: RagFilters,
    metadata_by_chunk_id: Mapping[str, RagResultMetadata],
) -> SearchResponse:
    """Convert prototype RAG results into the strict shared search contract.

    The adapter assigns request-local C1, C2, ... labels in result order. It
    converts ``retrieved_at`` to ``collected_at`` but never invents other source
    metadata; every missing enrichment record is an explicit integration error.
    """

    converted_results: list[dict[str, object]] = []
    seen_chunk_ids: set[str] = set()
    for expected_rank, result in enumerate(results, start=1):
        if result.chunk_id in seen_chunk_ids:
            raise IntegrationAdapterError(
                f"중복된 RAG chunk_id입니다: {result.chunk_id}"
            )
        seen_chunk_ids.add(result.chunk_id)
        if result.rank != expected_rank:
            raise IntegrationAdapterError(
                "RagResult는 rank 1부터 순서대로 전달되어야 합니다. "
                f"예상 rank={expected_rank}, 실제 rank={result.rank}"
            )
        metadata = metadata_by_chunk_id.get(result.chunk_id)
        if metadata is None:
            raise IntegrationAdapterError(
                f"공통 검색 계약에 필요한 metadata가 없습니다: {result.chunk_id}"
            )
        if not metadata.official_verified:
            raise IntegrationAdapterError(
                f"공식 검증되지 않은 검색 결과는 변환할 수 없습니다: {result.chunk_id}"
            )
        if metadata.quality_status != "approved":
            raise IntegrationAdapterError(
                f"품질 승인되지 않은 검색 결과는 변환할 수 없습니다: {result.chunk_id}"
            )

        converted_results.append(
            {
                "citation_id": f"C{expected_rank}",
                "rank": expected_rank,
                "document_id": result.document_id,
                "chunk_id": result.chunk_id,
                "chunk_index": metadata.chunk_index,
                "title": result.title,
                "publisher": metadata.publisher,
                "section": result.section,
                "content": result.content,
                "source_url": result.source_url,
                "source_anchor": metadata.source_anchor,
                "language": metadata.language,
                "source_type": metadata.source_type,
                "published_at": metadata.published_at,
                "updated_at": metadata.updated_at,
                "collected_at": _collected_at(result.retrieved_at),
                "indexed_at": metadata.indexed_at,
                "document_version": result.document_version,
                "license": result.license,
                "product_models": list(metadata.product_models),
                "use_cases": list(metadata.use_cases),
                "tasks": list(metadata.tasks),
                "categories": list(metadata.categories),
                "os_versions": list(metadata.os_versions),
                "document_checksum": metadata.document_checksum,
                "chunk_checksum": metadata.chunk_checksum,
                "embedding_checksum": metadata.embedding_checksum,
                "parser_version": metadata.parser_version,
                "official_verified": True,
                "quality_status": "approved",
                "image_url": metadata.image_url,
                "video_url": metadata.video_url,
            }
        )

    return SearchResponse.model_validate(
        {
            "schema_version": "1.1.0",
            "query_id": query_id,
            "query_language": query_language,
            "retrieval_method": retrieval_method,
            "top_k": top_k,
            "applied_filters": {
                "product_models": list(applied_filters.product_models),
                "use_cases": list(applied_filters.use_cases),
                "os_versions": list(applied_filters.os_versions),
                "source_types": list(applied_filters.source_types),
                "official_only": applied_filters.official_only,
            },
            "results": converted_results,
        }
    )


__all__ = [
    "IntegrationAdapterError",
    "RagResultMetadata",
    "condition_payload_to_rag_filters",
    "rag_results_to_search_response",
]
